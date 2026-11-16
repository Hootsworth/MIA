import logging
from datetime import datetime, timezone
from time import perf_counter
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.database import SessionLocal
from backend.detectors import DetectorInput, registry
from backend.detectors.roberta_openai import MODEL_ID, MODEL_REVISION
from backend.detectors.roberta_openai import DetectorInputError, ModelUnavailableError
from backend.models import AuditEvent, Detector, DetectorVersion, Document, Experiment, Result

ROOT = Path(__file__).resolve().parents[2]
STORAGE = ROOT / "storage" / "documents"

router = APIRouter(tags=["detectors"])
logger = logging.getLogger(__name__)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _records(db: Session):
    detector = db.scalar(select(Detector).where(Detector.name == "roberta-openai"))
    if detector is None:
        detector = Detector(name="roberta-openai", metadata_json={"model_id": MODEL_ID, "revision": MODEL_REVISION})
        db.add(detector)
        db.flush()
    version = db.scalar(select(DetectorVersion).where(DetectorVersion.detector_id == detector.id, DetectorVersion.version == MODEL_REVISION))
    if version is None:
        version = DetectorVersion(
            detector_id=detector.id,
            version=MODEL_REVISION,
            metadata_json={"model_id": MODEL_ID, "revision": MODEL_REVISION, "labels": ["Fake", "Real"]},
        )
        db.add(version)
        db.flush()
    return detector, version


def _cache_state(adapter):
    has_weights, cache_error = adapter.cache_status()
    return has_weights, cache_error


def _registry_view(db: Session):
    adapter = registry.get("roberta-openai")
    metadata = adapter.metadata()
    detector, version = _records(db)
    detector_state = dict(detector.metadata_json or {})
    health = detector_state.get("health_check")
    has_weights, cache_error = _cache_state(adapter)
    if cache_error:
        status = "unavailable"
        reason = cache_error
    elif not health or not health.get("available"):
        status = "not_checked" if not health else "unavailable"
        reason = None if not health else health.get("failure_reason")
        if not health:
            reason = "Weights are cached, but no successful real inference health check is recorded."
    else:
        status = "operational"
        reason = None
    return {
        "id": detector.id,
        "key": metadata.key,
        "name": metadata.name,
        "model_id": metadata.model_id,
        "revision": metadata.revision,
        "version_id": version.id,
        "version": version.version,
        "labels": ["Fake", "Real"],
        "supported_languages": list(metadata.languages),
        "minimum_words": metadata.min_words,
        "max_sequence_length": metadata.max_sequence_length,
        "score_semantics": metadata.score_semantics,
        "training_summary": metadata.training_summary,
        "limitations": list(metadata.limitations),
        "status": status,
        "device": health.get("device") if health else None,
        "last_health_check": health,
        "failure_reason": reason,
        "weights_cached": has_weights,
    }


@router.get("/detectors")
def list_detectors(db: Session = Depends(get_db)):
    payload = _registry_view(db)
    db.commit()
    return [payload]


@router.post("/detectors/{detector_key}/health")
def detector_health(detector_key: str, db: Session = Depends(get_db)):
    if detector_key != "roberta-openai":
        raise HTTPException(404, f"Unknown detector '{detector_key}'.")
    adapter = registry.get(detector_key)
    detector, version = _records(db)
    started = perf_counter()
    health = adapter.health_check()
    record = health.to_dict()
    record["duration_ms"] = (perf_counter() - started) * 1000
    record["available"] = bool(health.available)
    version_state = dict(version.metadata_json or {})
    version_state["last_health_check"] = record
    version.metadata_json = version_state
    detector_state = dict(detector.metadata_json or {})
    detector_state["health_check"] = record
    detector.metadata_json = detector_state
    db.add(AuditEvent(
        event_type="DETECTOR_HEALTH_CHECKED",
        entity_id=detector.id,
        details={"available": record["available"], "revision": health.revision, "device": health.device, "failure_reason": health.failure_reason},
    ))
    db.commit()
    response = _registry_view(db)
    if not health.available:
        response["status"] = "unavailable"
        response["failure_reason"] = health.failure_reason
        return response
    return response


@router.post("/detectors/{detector_key}/documents/{document_id}/predict")
def predict_document(detector_key: str, document_id: str, db: Session = Depends(get_db)):
    if detector_key != "roberta-openai":
        raise HTTPException(404, f"Unknown detector '{detector_key}'.")
    doc = db.get(Document, document_id)
    if not doc or (doc.metadata_json or {}).get("deleted"):
        raise HTTPException(404, "Document not found")
    declared = (doc.metadata_json or {}).get("declared", {})
    language = str(declared.get("language", ""))
    extraction_path = (ROOT / (doc.metadata_json or {}).get("extracted_path", "")).resolve()
    if not extraction_path.is_relative_to(STORAGE.resolve()) or not extraction_path.is_file():
        raise HTTPException(422, "Stored extracted text is missing or outside document storage.")
    import json
    try:
        text = json.loads(extraction_path.read_text(encoding="utf-8"))["raw_text"]
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(422, f"Could not read stored extracted text: {exc}") from exc
    adapter = registry.get(detector_key)
    document = DetectorInput(document_id=doc.id, text=text, language=language)
    validation = adapter.validate(document)
    if not validation.valid:
        raise HTTPException(422, {"message": "Detector input rejected", "errors": list(validation.errors), "word_count": validation.word_count})
    detector, version = _records(db)
    detector_state = dict(detector.metadata_json or {})
    health = detector_state.get("health_check") or {}
    if not health.get("available"):
        reason = health.get("failure_reason") or "Run a successful real-inference health check before predicting."
        raise HTTPException(503, {"message": "Detector is unavailable", "failure_reason": reason})
    has_weights, cache_error = _cache_state(adapter)
    if not has_weights:
        raise HTTPException(503, {"message": "Detector is unavailable", "failure_reason": cache_error})

    timestamp = datetime.now(timezone.utc)
    experiment = Experiment(
        name=f"Single detector run: {doc.filename}",
        status="RUNNING",
        protocol={
            "kind": "single_document_detector_run",
            "protocol_version": "m3.1",
            "document_id": doc.id,
            "document_sha256": doc.sha256,
            "detector_id": detector.id,
            "detector_version_id": version.id,
            "classification_rule": None,
            "note": "No binary metrics or authorship conclusion are produced by this one-document inference.",
        },
    )
    db.add(experiment)
    db.flush()
    started = perf_counter()
    try:
        prediction = adapter.predict(document, detector.id, version.id)
        output = prediction.to_dict()
        output["experiment_id"] = experiment.id
        output["provenance"] = declared.get("provenance")
        experiment.status = "COMPLETED"
    except Exception as exc:
        duration_ms = (perf_counter() - started) * 1000
        error = {"type": type(exc).__name__, "message": str(exc)}
        output = {
            "document_id": doc.id,
            "detector_id": detector.id,
            "detector_version_id": version.id,
            "experiment_id": experiment.id,
            "model_id": MODEL_ID,
            "revision": MODEL_REVISION,
            "configuration": {"minimum_words": adapter.metadata().min_words},
            "raw_output": {},
            "label": None,
            "score": None,
            "score_semantics": "unknown",
            "duration_ms": duration_ms,
            "device": getattr(adapter, "_device", None),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": error,
            "provenance": declared.get("provenance"),
        }
        experiment.status = "FAILED"
        experiment.protocol = {**experiment.protocol, "error": error}
    result = Result(
        experiment_id=experiment.id,
        document_id=doc.id,
        detector_version_id=version.id,
        output=output,
    )
    db.add(result)
    db.flush()
    db.add(AuditEvent(event_type="DETECTOR_PREDICTION_RECORDED", entity_id=doc.id, details={"result_id": result.id, "experiment_id": experiment.id, "error": output.get("error")}))
    db.commit()
    if output.get("error"):
        raise HTTPException(503, {"message": "Detector inference failed; no score was produced.", "result_id": result.id, "error": output["error"]})
    db.refresh(result)
    return {"result_id": result.id, **output}
