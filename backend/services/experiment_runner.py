"""Persistent, one-job-at-a-time experiment execution."""

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from backend.core.database import ROOT, SessionLocal
from backend.detectors import DetectorInput, registry
from backend.models import AuditEvent, Detector, Document, Experiment, Result

DOCUMENT_STORAGE = ROOT / "storage" / "documents"
_worker_lock = asyncio.Lock()
_tasks: set[asyncio.Task] = set()


def _now():
    return datetime.now(timezone.utc)


def recover_interrupted_experiments():
    """Convert runs lost with the previous process into resumable partial runs."""
    with SessionLocal() as db:
        rows = db.scalars(select(Experiment).where(Experiment.status == "RUNNING")).all()
        for experiment in rows:
            if not (experiment.protocol or {}).get("document_snapshot"):
                continue
            experiment.status = "PARTIALLY_COMPLETED"
            experiment.interruption_reason = "Backend stopped while the experiment was running. Resume to process missing document-detector pairs."
            experiment.cancel_requested = False
            experiment.finished_at = _now()
            db.add(AuditEvent(event_type="EXPERIMENT_INTERRUPTED", entity_id=experiment.id,
                              details={"completed_items": experiment.completed_items, "total_items": experiment.total_items}))
        db.commit()


def schedule_queued_experiments():
    """Resume work that was queued but not yet started when the process stopped."""
    with SessionLocal() as db:
        queued = db.scalars(select(Experiment.id).where(Experiment.status == "QUEUED")).all()
    for experiment_id in queued:
        schedule_experiment(experiment_id)


def schedule_experiment(experiment_id: str):
    task = asyncio.create_task(run_experiment(experiment_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


def _read_snapshot_text(snapshot: dict) -> str:
    path = (ROOT / snapshot["extracted_path"]).resolve()
    if not path.is_relative_to(DOCUMENT_STORAGE.resolve()):
        raise ValueError("Extracted text path is outside document storage")
    payload = json.loads(path.read_text(encoding="utf-8"))
    text = payload["raw_text"]
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != snapshot["extracted_sha256"]:
        raise ValueError("Extracted text changed after the experiment snapshot was created")
    return text


def _pair_key(document_snapshot: dict, detector_snapshot: dict) -> str:
    return f"{document_snapshot['id']}:{detector_snapshot['version_id']}"


def _record_pair(experiment_id: str, document_snapshot: dict, detector_snapshot: dict):
    with SessionLocal() as db:
        experiment = db.get(Experiment, experiment_id)
        if experiment is None:
            return
        doc = db.get(Document, document_snapshot["id"])
        detector_row = db.get(Detector, detector_snapshot["detector_id"])
        existing = db.scalar(select(Result).where(
            Result.experiment_id == experiment_id,
            Result.document_id == document_snapshot["id"],
            Result.detector_version_id == detector_snapshot["version_id"],
        ))
        attempt_number = int(((existing.output or {}).get("attempt_number", 0)) if existing else 0) + 1
        output = {
            "document_id": document_snapshot["id"],
            "detector_id": detector_snapshot["detector_id"],
            "detector_version_id": detector_snapshot["version_id"],
            "model_id": detector_snapshot["model_id"],
            "revision": detector_snapshot["revision"],
            "configuration": {"seed": experiment.protocol["seed"], "conditions": experiment.protocol["conditions"]},
            "raw_output": {}, "label": None, "score": None, "score_semantics": "unknown",
            "duration_ms": 0.0, "device": None, "error": None,
            "provenance": document_snapshot["provenance"], "attempt_number": attempt_number,
        }
        try:
            if doc is None:
                raise ValueError("Snapshot document no longer exists")
            if (doc.metadata_json or {}).get("deleted"):
                raise ValueError("Snapshot document has been archived")
            if doc.sha256 != document_snapshot["sha256"]:
                raise ValueError("Document hash differs from the frozen experiment snapshot")
            adapter = registry.get(detector_snapshot["key"])
            declared = (doc.metadata_json or {}).get("declared", {})
            text = _read_snapshot_text(document_snapshot)
            validation = adapter.validate(DetectorInput(doc.id, text, str(declared.get("language", ""))))
            if not validation.valid:
                raise ValueError("; ".join(validation.errors))
            if detector_row is None:
                raise ValueError("Detector record no longer exists")
            health = (detector_row.metadata_json or {}).get("health_check") or {}
            if not health.get("available"):
                raise RuntimeError(health.get("failure_reason") or "Detector needs a successful real health check before running")
            available, reason = adapter.resource_status() if hasattr(adapter, "resource_status") else adapter.cache_status()
            if not available:
                raise RuntimeError(reason or "Detector resources are unavailable")
            prediction = adapter.predict(DetectorInput(doc.id, text, str(declared.get("language", ""))),
                                        detector_snapshot["detector_id"], detector_snapshot["version_id"])
            output.update(prediction.to_dict())
            output["provenance"] = document_snapshot["provenance"]
        except Exception as exc:
            output["error"] = {"type": type(exc).__name__, "message": str(exc)}
            output["score"] = None
        if existing:
            existing.output = output
        else:
            db.add(Result(experiment_id=experiment_id, document_id=document_snapshot["id"],
                          detector_version_id=detector_snapshot["version_id"], output=output))
            experiment.completed_items += 1
        db.add(AuditEvent(event_type="EXPERIMENT_ITEM_RECORDED", entity_id=experiment_id,
                          details={"document_id": document_snapshot["id"], "detector_key": detector_snapshot["key"],
                                   "error": output["error"]}))
        db.commit()


def _next_pair(experiment_id: str, attempted: set[str]):
    with SessionLocal() as db:
        experiment = db.get(Experiment, experiment_id)
        if experiment is None:
            return "missing", None
        if experiment.cancel_requested:
            experiment.status = "CANCELLED"
            experiment.cancel_requested = False
            experiment.finished_at = _now()
            db.add(AuditEvent(event_type="EXPERIMENT_CANCELLED", entity_id=experiment_id,
                              details={"completed_items": experiment.completed_items, "total_items": experiment.total_items}))
            db.commit()
            return "cancelled", None
        protocol = experiment.protocol
        for document in protocol["document_snapshot"]:
            for detector in protocol["detector_snapshot"]:
                exists = db.scalar(select(Result.id).where(
                    Result.experiment_id == experiment_id,
                    Result.document_id == document["id"],
                    Result.detector_version_id == detector["version_id"],
                ))
                key = _pair_key(document, detector)
                row = db.get(Result, exists) if exists else None
                if (not row or (row.output or {}).get("error")) and key not in attempted:
                    return "pair", (document, detector)
        results = db.scalars(select(Result).where(Result.experiment_id == experiment_id)).all()
        failed = sum(1 for result in results if (result.output or {}).get("error"))
        experiment.status = "PARTIALLY_COMPLETED" if failed else "COMPLETED"
        experiment.finished_at = _now()
        experiment.completed_items = len(results)
        experiment.interruption_reason = None
        db.add(AuditEvent(event_type="EXPERIMENT_FINISHED", entity_id=experiment_id,
                          details={"status": experiment.status, "completed_items": len(results),
                                   "total_items": experiment.total_items, "failures": failed}))
        db.commit()
        return "finished", None


def _mark_worker_failed(experiment_id: str, exc: Exception):
    with SessionLocal() as db:
        experiment = db.get(Experiment, experiment_id)
        if experiment is None or experiment.status != "RUNNING":
            return
        experiment.status = "FAILED"
        experiment.finished_at = _now()
        experiment.interruption_reason = f"Experiment worker failed: {type(exc).__name__}: {exc}"
        db.add(AuditEvent(event_type="EXPERIMENT_WORKER_FAILED", entity_id=experiment_id,
                          details={"type": type(exc).__name__, "message": str(exc)}))
        db.commit()


async def run_experiment(experiment_id: str):
    async with _worker_lock:
        with SessionLocal() as db:
            experiment = db.get(Experiment, experiment_id)
            if experiment is None or experiment.status != "QUEUED":
                return
            experiment.status = "RUNNING"
            experiment.started_at = experiment.started_at or _now()
            experiment.finished_at = None
            experiment.interruption_reason = None
            experiment.total_items = len(experiment.protocol["document_snapshot"]) * len(experiment.protocol["detector_snapshot"])
            db.add(AuditEvent(event_type="EXPERIMENT_STARTED", entity_id=experiment_id,
                              details={"total_items": experiment.total_items}))
            db.commit()
        attempted: set[str] = set()
        try:
            while True:
                state, pair = await asyncio.to_thread(_next_pair, experiment_id, attempted)
                if state != "pair":
                    return
                attempted.add(_pair_key(pair[0], pair[1]))
                await asyncio.to_thread(_record_pair, experiment_id, pair[0], pair[1])
        except Exception as exc:
            await asyncio.to_thread(_mark_worker_failed, experiment_id, exc)
