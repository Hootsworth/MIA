import copy
import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.detectors import _records, get_db
from backend.core.database import ROOT
from backend.detectors import registry
from backend.models import AuditEvent, Detector, Document, Experiment, ExperimentDocument, Result, TurnitinReport
from backend.schemas.experiments import ExperimentCreate
from backend.services.experiment_runner import schedule_experiment

router = APIRouter(tags=["experiments"])
DOCUMENT_STORAGE = ROOT / "storage" / "documents"


def _snapshot(payload: ExperimentCreate, db: Session) -> dict:
    documents = db.scalars(select(Document).where(Document.id.in_(payload.document_ids))).all()
    by_id = {doc.id: doc for doc in documents}
    missing = [doc_id for doc_id in payload.document_ids if doc_id not in by_id]
    if missing:
        raise HTTPException(404, {"message": "Unknown document IDs", "document_ids": missing})
    document_snapshot = []
    for doc_id in payload.document_ids:
        doc = by_id[doc_id]
        metadata = doc.metadata_json or {}
        if metadata.get("deleted"):
            raise HTTPException(409, f"Document {doc.filename} is deleted")
        extracted_rel = metadata.get("extracted_path")
        if not extracted_rel:
            raise HTTPException(422, f"Document {doc.filename} has no stored extracted text")
        extracted_path = (ROOT / extracted_rel).resolve()
        if not extracted_path.is_relative_to(DOCUMENT_STORAGE.resolve()):
            raise HTTPException(422, f"Document {doc.filename} has an unsafe extracted-text path")
        try:
            text = json.loads(extracted_path.read_text(encoding="utf-8"))["raw_text"]
        except (OSError, ValueError, KeyError) as exc:
            raise HTTPException(422, f"Document {doc.filename} has unreadable extracted text: {exc}") from exc
        declared = metadata.get("declared", {})
        document_snapshot.append({
            "id": doc.id,
            "filename": doc.filename,
            "sha256": doc.sha256,
            "extracted_path": str(extracted_path.relative_to(ROOT)),
            "extracted_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "provenance": declared.get("provenance"),
            "language": declared.get("language"),
            "domain": declared.get("domain"),
            "genre": declared.get("genre"),
            "author_language_background": declared.get("author_language_background"),
            "word_count": metadata.get("word_count"),
            "source_group": declared.get("source_group") or declared.get("source"),
            "duplicate_group": declared.get("duplicate_group"),
        })
    detector_snapshot = []
    for key in payload.detector_keys:
        try:
            adapter = registry.get(key)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        detector, version = _records(db, adapter)
        metadata = adapter.metadata()
        detector_snapshot.append({
            "key": key,
            "detector_id": detector.id,
            "version_id": version.id,
            "model_id": metadata.model_id,
            "revision": metadata.revision,
            "score_semantics": metadata.score_semantics,
        })
    return {
        "research_question": payload.research_question,
        "hypothesis": payload.hypothesis,
        "document_snapshot": document_snapshot,
        "detector_snapshot": detector_snapshot,
        "conditions": payload.conditions,
        "transformations": payload.conditions.get("transformations", []),
        "seed": payload.seed,
        "protocol_version": payload.protocol_version,
        "classification_rule": payload.classification_rule,
        "metrics": payload.metrics,
    }


def _result_view(result: Result, filename: str | None = None):
    output = result.output or {}
    return {
        "id": result.id,
        "document_id": result.document_id,
        "filename": filename,
        "detector_version_id": result.detector_version_id,
        "output": output,
        "error": output.get("error"),
        "created_at": result.created_at.isoformat(),
    }


def _view(experiment: Experiment, results: list[Result] | None = None, docs: dict | None = None):
    protocol = experiment.protocol or {}
    return {
        "id": experiment.id,
        "name": experiment.name,
        "status": experiment.status,
        "research_question": protocol.get("research_question"),
        "hypothesis": protocol.get("hypothesis"),
        "protocol": protocol,
        "progress": {"completed": experiment.completed_items, "total": experiment.total_items,
                      "failures": sum(bool((row.output or {}).get("error")) for row in results or [])},
        "started_at": experiment.started_at.isoformat() if experiment.started_at else None,
        "finished_at": experiment.finished_at.isoformat() if experiment.finished_at else None,
        "interruption_reason": experiment.interruption_reason,
        "results": [_result_view(row, (docs or {}).get(row.document_id)) for row in (results or [])],
    }


def _details(db: Session, experiment: Experiment):
    results = db.scalars(select(Result).where(Result.experiment_id == experiment.id).order_by(Result.created_at, Result.id)).all()
    protocol = experiment.protocol or {}
    snapshot_ids = [item["id"] for item in protocol.get("document_snapshot", [])]
    ids = set(snapshot_ids) | {result.document_id for result in results}
    docs = {doc.id: doc.filename for doc in db.scalars(select(Document).where(Document.id.in_(ids))).all()} if ids else {}
    view = _view(experiment, results, docs)
    if snapshot_ids:
        reports = db.scalars(select(TurnitinReport).where(TurnitinReport.document_id.in_(snapshot_ids)).order_by(TurnitinReport.created_at)).all()
        for report in reports:
            data = report.report_data or {}
            ai = data.get("ai_writing", {})
            view["results"].append({
                "id": report.id, "document_id": report.document_id, "filename": docs.get(report.document_id),
                "detector_name": "Turnitin report (manual import)", "detector_version_id": data.get("detector_version"),
                "output": {"score": ai.get("value"), "score_semantics": "percentage", "turnitin": data},
                "error": None, "created_at": report.created_at.isoformat(),
            })
    return view


@router.post("/experiments", status_code=201)
def create_experiment(payload: ExperimentCreate, db: Session = Depends(get_db)):
    experiment = Experiment(name=payload.name, status="DRAFT", protocol=_snapshot(payload, db))
    db.add(experiment)
    db.flush()
    for doc_id in payload.document_ids:
        db.add(ExperimentDocument(experiment_id=experiment.id, document_id=doc_id))
    db.add(AuditEvent(event_type="EXPERIMENT_CREATED", entity_id=experiment.id,
                      details={"document_count": len(payload.document_ids), "detector_count": len(payload.detector_keys)}))
    db.commit()
    db.refresh(experiment)
    return _view(experiment)


@router.get("/experiments")
def list_experiments(db: Session = Depends(get_db)):
    rows = db.scalars(select(Experiment).order_by(Experiment.created_at.desc())).all()
    return [_details(db, row) for row in rows]


@router.get("/experiments/{experiment_id}")
def get_experiment(experiment_id: str, db: Session = Depends(get_db)):
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(404, "Experiment not found")
    return _details(db, experiment)


@router.patch("/experiments/{experiment_id}")
def update_draft(experiment_id: str, payload: ExperimentCreate, db: Session = Depends(get_db)):
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(404, "Experiment not found")
    if experiment.status != "DRAFT":
        raise HTTPException(409, "Experiment protocol is frozen once it is queued")
    experiment.name = payload.name
    experiment.protocol = _snapshot(payload, db)
    db.execute(ExperimentDocument.__table__.delete().where(ExperimentDocument.experiment_id == experiment_id))
    for doc_id in payload.document_ids:
        db.add(ExperimentDocument(experiment_id=experiment.id, document_id=doc_id))
    db.add(AuditEvent(event_type="EXPERIMENT_DRAFT_UPDATED", entity_id=experiment.id,
                      details={"document_count": len(payload.document_ids), "detector_count": len(payload.detector_keys)}))
    db.commit()
    db.refresh(experiment)
    return _details(db, experiment)


@router.post("/experiments/{experiment_id}/duplicate", status_code=201)
def duplicate_experiment(experiment_id: str, db: Session = Depends(get_db)):
    source = db.get(Experiment, experiment_id)
    if source is None:
        raise HTTPException(404, "Experiment not found")
    protocol = copy.deepcopy(source.protocol or {})
    duplicate = Experiment(name=f"{source.name} (copy)", status="DRAFT", protocol=protocol)
    db.add(duplicate)
    db.flush()
    for document in protocol.get("document_snapshot", []):
        db.add(ExperimentDocument(experiment_id=duplicate.id, document_id=document["id"]))
    db.add(AuditEvent(event_type="EXPERIMENT_DUPLICATED", entity_id=duplicate.id,
                      details={"source_experiment_id": source.id}))
    db.commit()
    db.refresh(duplicate)
    return _view(duplicate)


@router.post("/experiments/{experiment_id}/run", status_code=202)
async def queue_experiment(experiment_id: str, db: Session = Depends(get_db)):
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(404, "Experiment not found")
    if experiment.status != "DRAFT":
        raise HTTPException(409, "Only a draft experiment can be queued")
    classification_rule = (experiment.protocol or {}).get("classification_rule")
    if not classification_rule or (isinstance(classification_rule, str) and not classification_rule.strip()):
        raise HTTPException(422, "A classification rule is required before running")
    experiment.status = "QUEUED"
    experiment.cancel_requested = False
    experiment.total_items = len(experiment.protocol["document_snapshot"]) * len(experiment.protocol["detector_snapshot"])
    experiment.finished_at = None
    db.add(AuditEvent(event_type="EXPERIMENT_QUEUED", entity_id=experiment.id,
                      details={"total_items": experiment.total_items}))
    db.commit()
    schedule_experiment(experiment.id)
    return _view(experiment)


@router.post("/experiments/{experiment_id}/cancel", status_code=202)
def cancel_experiment(experiment_id: str, db: Session = Depends(get_db)):
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(404, "Experiment not found")
    if experiment.status == "QUEUED":
        experiment.status = "CANCELLED"
        experiment.finished_at = datetime.now(timezone.utc)
    elif experiment.status == "RUNNING":
        experiment.cancel_requested = True
    else:
        raise HTTPException(409, f"Cannot cancel an experiment in {experiment.status} state")
    db.add(AuditEvent(event_type="EXPERIMENT_CANCEL_REQUESTED", entity_id=experiment.id, details={"status": experiment.status}))
    db.commit()
    return _details(db, experiment)


@router.post("/experiments/{experiment_id}/resume", status_code=202)
async def resume_experiment(experiment_id: str, db: Session = Depends(get_db)):
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(404, "Experiment not found")
    if experiment.status != "PARTIALLY_COMPLETED":
        raise HTTPException(409, "Only a partially completed or interrupted experiment can be resumed")
    experiment.status = "QUEUED"
    experiment.cancel_requested = False
    experiment.finished_at = None
    experiment.interruption_reason = None
    db.add(AuditEvent(event_type="EXPERIMENT_RESUMED", entity_id=experiment.id,
                      details={"completed_items": experiment.completed_items, "total_items": experiment.total_items}))
    db.commit()
    schedule_experiment(experiment.id)
    return _view(experiment)
