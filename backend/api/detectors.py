# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.database import SessionLocal
from backend.detectors import DetectorInput, registry
from backend.models import AuditEvent, Detector, DetectorVersion, Document, Experiment, Result

router = APIRouter(tags=["detectors"])
logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
STORAGE = ROOT / "storage" / "documents"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _records(db: Session, adapter):
    metadata = adapter.metadata()
    detector = db.scalar(select(Detector).where(Detector.name == metadata.key))
    if detector is None:
        detector = Detector(name=metadata.key, metadata_json={"model_id": metadata.model_id, "revision": metadata.revision})
        db.add(detector)
        db.flush()
    version = db.scalar(select(DetectorVersion).where(
        DetectorVersion.detector_id == detector.id,
        DetectorVersion.version == metadata.revision,
    ))
    if version is None:
        version = DetectorVersion(
            detector_id=detector.id,
            version=metadata.revision,
            metadata_json={"model_id": metadata.model_id, "revision": metadata.revision},
        )
        db.add(version)
        db.flush()
    return detector, version


def _resource_status(adapter):
    status = getattr(adapter, "resource_status", None) or getattr(adapter, "cache_status", None)
    if status is None:
        return True, None
    return status()


def _registry_view(db: Session, key: str):
    adapter = registry.get(key)
    metadata = adapter.metadata()
    detector, version = _records(db, adapter)
    detector_state = dict(detector.metadata_json or {})
    health = detector_state.get("health_check")
    has_resource, resource_error = _resource_status(adapter)
    if not has_resource:
        status, reason = "unavailable", resource_error
    elif not health:
        status = "not_checked"
        reason = "Available resources are present, but no successful real inference health check is recorded."
    elif not health.get("available"):
        status, reason = "unavailable", health.get("failure_reason")
    else:
        status, reason = "operational", None
    version_metadata = version.metadata_json or {}
    return {
        "id": detector.id,
        "key": metadata.key,
        "name": metadata.name,
        "model_id": metadata.model_id,
        "revision": metadata.revision,
        "version_id": version.id,
        "version": version.version,
        "labels": version_metadata.get("labels", []),
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
        "weights_cached": bool(has_resource),
        "resource_available": bool(has_resource),
        "resource_label": "reference index" if metadata.key == "mia-similarity-winnowing" else "model weights",
    }


@router.get("/detectors")
def list_detectors(db: Session = Depends(get_db)):
    payload = [_registry_view(db, key) for key in registry.keys()]
    db.commit()
    return payload


@router.post("/detectors/{detector_key}/health")
def detector_health(detector_key: str, db: Session = Depends(get_db)):
    try:
        adapter = registry.get(detector_key)
    except KeyError as exc:
        raise HTTPException(404, f"Unknown detector '{detector_key}'.") from exc
    detector, version = _records(db, adapter)
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
        details={"available": record["available"], "revision": health.revision,
                 "device": health.device, "failure_reason": health.failure_reason},
    ))
    db.commit()
    return _registry_view(db, detector_key)


@router.post("/detectors/{detector_key}/documents/{document_id}/predict")
def predict_document(detector_key: str, document_id: str, db: Session = Depends(get_db)):
    try:
        adapter = registry.get(detector_key)
    except KeyError as exc:
        raise HTTPException(404, f"Unknown detector '{detector_key}'.") from exc
    doc = db.get(Document, document_id)
    if not doc or (doc.metadata_json or {}).get("deleted"):
        raise HTTPException(404, "Document not found")
    declared = (doc.metadata_json or {}).get("declared", {})
    extraction_path = (ROOT / (doc.metadata_json or {}).get("extracted_path", "")).resolve()
    if not extraction_path.is_relative_to(STORAGE.resolve()) or not extraction_path.is_file():
        raise HTTPException(422, "Stored extracted text is missing or outside document storage.")
    try:
        text = json.loads(extraction_path.read_text(encoding="utf-8"))["raw_text"]
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(422, f"Could not read stored extracted text: {exc}") from exc
    detector, version = _records(db, adapter)
    validation = adapter.validate(DetectorInput(document_id=doc.id, text=text, language=str(declared.get("language", ""))))
    if not validation.valid:
        raise HTTPException(422, {"message": "Detector input rejected", "errors": list(validation.errors), "word_count": validation.word_count})
    detector_state = dict(detector.metadata_json or {})
    health = detector_state.get("health_check") or {}
    if not health.get("available"):
        reason = health.get("failure_reason") or "Run a successful real-inference health check before predicting."
        raise HTTPException(503, {"message": "Detector is unavailable", "failure_reason": reason})
    has_resource, resource_error = _resource_status(adapter)
    if not has_resource:
        raise HTTPException(503, {"message": "Detector is unavailable", "failure_reason": resource_error})

    experiment = Experiment(
        name=f"Single detector run: {doc.filename}",
        status="RUNNING",
        protocol={
            "kind": "single_document_detector_run",
            "protocol_version": "m4.1" if detector_key == "mia-similarity-winnowing" else "m3.1",
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
        prediction = adapter.predict(
            DetectorInput(document_id=doc.id, text=text, language=str(declared.get("language", ""))),
            detector.id,
            version.id,
        )
        output = prediction.to_dict()
        output["experiment_id"] = experiment.id
        output["provenance"] = declared.get("provenance")
        experiment.status = "COMPLETED"
    except Exception as exc:
        logger.exception("Detector inference failed for %s", detector_key)
        error = {"type": type(exc).__name__, "message": str(exc)}
        output = {
            "document_id": doc.id,
            "detector_id": detector.id,
            "detector_version_id": version.id,
            "experiment_id": experiment.id,
            "model_id": adapter.metadata().model_id,
            "revision": adapter.metadata().revision,
            "configuration": {},
            "raw_output": {},
            "label": None,
            "score": None,
            "score_semantics": "unknown",
            "duration_ms": (perf_counter() - started) * 1000,
            "device": None,
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
    db.add(AuditEvent(
        event_type="DETECTOR_PREDICTION_RECORDED",
        entity_id=doc.id,
        details={"result_id": result.id, "experiment_id": experiment.id, "error": output.get("error")},
    ))
    db.commit()
    if output.get("error"):
        raise HTTPException(503, {"message": "Detector inference failed; no score was produced.", "result_id": result.id, "error": output["error"]})
    db.refresh(result)
    return {"result_id": result.id, **output}
