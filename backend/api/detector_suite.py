# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
"""Persist one document's outputs from the local open detector suite."""

import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.detectors import _records, _resource_status, get_db
from backend.detectors import DetectorInput, registry
from backend.models import AuditEvent, Document, Experiment, Result

router = APIRouter(tags=["detector-suite"])
ROOT = Path(__file__).resolve().parents[2]
DOCUMENT_STORAGE = ROOT / "storage" / "documents"
DETECTOR_KEYS = ("tropa-mini", "modernbert-ai-text-detector")


def _load_extracted_text(document):
    metadata = document.metadata_json or {}
    raw_path = (ROOT / metadata.get("extracted_path", "")).resolve()
    if not raw_path.is_relative_to(DOCUMENT_STORAGE.resolve()) or not raw_path.is_file():
        raise HTTPException(422, "Stored extracted text is missing or outside document storage")
    try:
        return json.loads(raw_path.read_text(encoding="utf-8"))["raw_text"]
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(422, f"Could not read stored extracted text: {exc}") from exc


@router.post("/detector-suite/documents/{document_id}/predict")
def predict_suite(document_id: str, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if document is None or (document.metadata_json or {}).get("deleted"):
        raise HTTPException(404, "Document not found")
    metadata = (document.metadata_json or {}).get("declared", {})
    detector_input = DetectorInput(document_id=document.id, text=_load_extracted_text(document),
                                   language=str(metadata.get("language", "")))
    records = []
    adapters = []
    for key in DETECTOR_KEYS:
        adapter = registry.get(key)
        result = adapter.validate(detector_input)
        if not result.valid:
            raise HTTPException(422, {"message": f"{adapter.metadata().name} rejected the document", "errors": list(result.errors), "word_count": result.word_count})
        available, reason = _resource_status(adapter)
        if not available:
            raise HTTPException(503, {"message": f"{adapter.metadata().name} weights are unavailable", "failure_reason": reason})
        detector, version = _records(db, adapter)
        detector_state = dict(detector.metadata_json or {})
        health = detector_state.get("health_check") or {}
        if not health.get("available") or health.get("revision") != adapter.metadata().revision:
            started = perf_counter()
            checked = adapter.health_check()
            health = checked.to_dict()
            health["duration_ms"] = (perf_counter() - started) * 1000
            health["available"] = bool(checked.available)
            version_state = dict(version.metadata_json or {})
            version_state["last_health_check"] = health
            version.metadata_json = version_state
            detector_state["health_check"] = health
            detector.metadata_json = detector_state
            db.add(AuditEvent(event_type="DETECTOR_HEALTH_CHECKED", entity_id=detector.id,
                              details={"available": health["available"], "revision": health["revision"],
                                       "device": health.get("device"), "failure_reason": health.get("failure_reason")}))
        if not health.get("available"):
            raise HTTPException(503, {"message": f"{adapter.metadata().name} failed its real inference check", "failure_reason": health.get("failure_reason")})
        records.append((adapter, detector, version))
        adapters.append(adapter)

    experiment = Experiment(
        name=f"Open detector suite: {document.filename}", status="RUNNING", total_items=len(adapters),
        protocol={"kind": "single_document_detector_suite_run", "document_id": document.id,
                  "document_sha256": document.sha256, "document_filename": document.filename,
                  "detector_snapshot": [{"key": adapter.metadata().key, "version_id": version.id,
                                         "model_id": adapter.metadata().model_id, "revision": adapter.metadata().revision,
                                         "score_semantics": adapter.metadata().score_semantics}
                                        for adapter, _, version in records],
                  "note": "Detector outputs are reported side by side; their scores are not averaged or calibrated as authorship probabilities."},
    )
    db.add(experiment)
    db.flush()
    results = []
    try:
        for adapter, detector, version in records:
            prediction = adapter.predict(detector_input, detector.id, version.id)
            output = prediction.to_dict()
            output["experiment_id"] = experiment.id
            output["provenance"] = metadata.get("provenance", "UNKNOWN")
            row = Result(experiment_id=experiment.id, document_id=document.id,
                         detector_version_id=version.id, output=output)
            db.add(row)
            db.flush()
            results.append({"result_id": row.id, "detector": adapter.metadata().key,
                            "name": adapter.metadata().name, "model_id": prediction.model_id,
                            "revision": prediction.revision, "label": prediction.label,
                            "score": prediction.score, "score_semantics": prediction.score_semantics,
                            "raw_output": prediction.raw_output, "device": prediction.device,
                            "duration_ms": prediction.duration_ms})
        experiment.status = "COMPLETED"
        experiment.completed_items = len(results)
        experiment.total_items = len(results)
        db.add(AuditEvent(event_type="DETECTOR_SUITE_COMPLETED", entity_id=experiment.id,
                          details={"document_id": document.id, "detectors": [row["detector"] for row in results]}))
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(503, f"Local detector suite could not complete: {exc}") from exc
    return {"experiment_id": experiment.id, "document_id": document.id, "filename": document.filename,
            "word_count": (document.metadata_json or {}).get("word_count", 0), "results": results,
            "note": "Independent model outputs are shown side by side. No combined verdict or authorship probability is calculated."}
