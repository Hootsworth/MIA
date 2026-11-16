# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
"""Manual, institution-authorised Turnitin report imports. No vendor API calls."""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.detectors import get_db
from backend.core.database import ROOT
from backend.models import AuditEvent, Document, TurnitinReport
from backend.schemas.turnitin import TurnitinImport, parse_score
from backend.services.document_ingestion import MAX_BYTES, safe_filename

router = APIRouter(tags=["turnitin reports"])
REPORT_STORAGE = ROOT / "storage" / "reports"
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


def _report_view(row: TurnitinReport):
    data = row.report_data or {}
    ai = data.get("ai_writing", {})
    similarity = data.get("similarity", {})
    return {
        "id": row.id,
        "document_id": row.document_id,
        "submission_reference": data.get("submission_reference"),
        "report_timestamp": data.get("report_timestamp"),
        "ingested_at": row.created_at.isoformat(),
        "similarity": similarity,
        "ai_writing": ai,
        "eligible_word_count": data.get("eligible_word_count"),
        "document_word_count": data.get("document_word_count"),
        "word_count_tolerance": data.get("word_count_tolerance"),
        "submitted_file_sha256": data.get("submitted_file_sha256"),
        "report_file_name": data.get("report_file_name"),
        "report_file_sha256": data.get("report_file_sha256"),
        "detector_version": data.get("detector_version"),
        "passages": data.get("passages", []),
        "score_semantics": "percentage",
    }


def _validate_file(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "Report file must be a PDF, PNG, or JPEG")
    valid = ((ext == ".pdf" and data.startswith(b"%PDF-")) or
             (ext == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n")) or
             (ext in {".jpg", ".jpeg"} and data.startswith(b"\xff\xd8\xff")))
    if not valid:
        raise HTTPException(415, "Report file content does not match its PDF/PNG/JPEG extension")
    return ext


@router.post("/turnitin-reports", status_code=201)
async def import_turnitin_report(payload: str = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        request = TurnitinImport.model_validate_json(payload)
    except ValidationError as exc:
        raise HTTPException(422, {"message": "Invalid Turnitin import fields", "errors": exc.errors(include_context=False)}) from exc
    doc = db.get(Document, request.document_id)
    if doc is None or (doc.metadata_json or {}).get("deleted"):
        raise HTTPException(404, "Selected document not found")
    if request.submitted_file_sha256.lower() != doc.sha256.lower():
        raise HTTPException(409, {"message": "Submitted-file hash does not match the stored original", "document_sha256": doc.sha256})
    word_count = int((doc.metadata_json or {}).get("word_count", 0))
    difference = abs(request.eligible_word_count - word_count)
    if difference > request.word_count_tolerance:
        raise HTTPException(409, {"message": "Eligible word count differs from the stored document count beyond the declared tolerance",
                                  "document_word_count": word_count, "eligible_word_count": request.eligible_word_count,
                                  "difference": difference, "tolerance": request.word_count_tolerance})
    filename = safe_filename(file.filename or "turnitin-report")
    if Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "Report file must be a PDF, PNG, or JPEG")
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(413, "Maximum report file size is 20 MB")
    try:
        extension = _validate_file(filename, content)
    except HTTPException:
        raise
    report_hash = hashlib.sha256(content).hexdigest()
    for existing in db.scalars(select(TurnitinReport)).all():
        existing_data = existing.report_data or {}
        if existing_data.get("report_file_sha256") == report_hash:
            if existing.document_id == doc.id:
                raise HTTPException(409, "This exact report file has already been imported for this document")
            raise HTTPException(409, "This exact report file is already associated with a different document")
    report_id = str(uuid.uuid4())
    folder = REPORT_STORAGE / report_id
    folder.mkdir(parents=True, exist_ok=False)
    report_path = folder / f"original{extension}"
    try:
        report_path.write_bytes(content)
        similarity_value = parse_score(request.similarity_raw_value, request.similarity_state, "similarity")
        ai_value = parse_score(request.ai_raw_value, request.ai_state, "AI-writing")
        report_data = {
            "schema_version": "m7.1",
            "submission_reference": request.submission_reference.strip(),
            "report_timestamp": request.report_timestamp.isoformat(),
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "similarity": {"raw": request.similarity_raw_value, "state": request.similarity_state,
                           "value": similarity_value, "censoring_upper_bound": request.similarity_censoring_upper_bound},
            "ai_writing": {"raw": request.ai_raw_value, "state": request.ai_state,
                           "value": ai_value, "censoring_upper_bound": request.ai_censoring_upper_bound},
            "eligible_word_count": request.eligible_word_count,
            "document_word_count": word_count,
            "word_count_tolerance": request.word_count_tolerance,
            "submitted_file_sha256": doc.sha256,
            "identity_confirmed": request.identity_confirmed,
            "confirmed_document_id": request.confirmed_document_id,
            "report_file_name": filename,
            "report_file_path": str(report_path.relative_to(ROOT)),
            "report_file_sha256": report_hash,
            "detector_version": request.detector_version,
            "passages": [passage.model_dump(mode="json") for passage in request.passages],
            "score_semantics": "percentage",
        }
        record = TurnitinReport(id=report_id, document_id=doc.id, report_data=report_data, raw_value=request.ai_raw_value)
        db.add(record)
        db.add(AuditEvent(event_type="TURNITIN_REPORT_IMPORTED", entity_id=doc.id,
                          details={"report_id": report_id, "report_file_sha256": report_hash,
                                   "submission_reference": request.submission_reference.strip()}))
        db.commit()
        db.refresh(record)
        return _report_view(record)
    except Exception:
        db.rollback()
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        raise


@router.get("/turnitin-reports")
def list_turnitin_reports(document_id: str | None = None, db: Session = Depends(get_db)):
    statement = select(TurnitinReport).order_by(TurnitinReport.created_at.desc())
    if document_id:
        statement = statement.where(TurnitinReport.document_id == document_id)
    return [_report_view(row) for row in db.scalars(statement).all()]


@router.get("/turnitin-reports/{report_id}")
def get_turnitin_report(report_id: str, db: Session = Depends(get_db)):
    report = db.get(TurnitinReport, report_id)
    if report is None:
        raise HTTPException(404, "Turnitin report not found")
    return _report_view(report)
