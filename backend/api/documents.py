# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
import csv
import hashlib
import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.database import SessionLocal
from backend.models import AuditEvent, Document
from backend.schemas.documents import DocumentMetadata
from backend.services.document_ingestion import MAX_BYTES, check_type, extract, safe_filename, shingle_set
from backend.services.language_detection import detect_language

router = APIRouter(tags=["documents"])
ROOT = Path(__file__).resolve().parents[2]
STORAGE = ROOT / "storage" / "documents"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def view(doc: Document):
    meta = doc.metadata_json or {}
    return {"id": doc.id, "filename": doc.filename, "sha256": doc.sha256,
            "created_at": doc.created_at.isoformat(), "updated_at": doc.updated_at.isoformat(),
            "metadata": meta.get("declared", {}), "word_count": meta.get("word_count", 0),
            "language_detection": meta.get("language_detection", {"status": "not_recorded"}),
            "quality_flags": meta.get("quality_flags", []), "duplicate_flags": meta.get("duplicate_flags", []),
            "deleted": bool(meta.get("deleted", False))}


def audit(db: Session, typ: str, entity_id: str, detail: dict):
    db.add(AuditEvent(event_type=typ, entity_id=entity_id, details=detail))


@router.post("/documents", status_code=201)
async def upload_document(file: UploadFile = File(...), metadata: str = Form(...), db: Session = Depends(get_db)):
    filename = safe_filename(file.filename or "upload")
    try:
        declared = DocumentMetadata.model_validate_json(metadata)
    except ValidationError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Maximum document size is 20 MB")
    ext = check_type(filename, data)
    digest = hashlib.sha256(data).hexdigest()
    existing = db.scalar(select(Document).where(Document.sha256 == digest))
    if existing:
        raise HTTPException(409, {"message": "Exact duplicate document", "existing_document_id": existing.id, "existing_filename": existing.filename})
    pages, text, word_count, flags = extract(ext, data)
    if declared.language.strip().lower() in {"", "auto", "und", "unknown"}:
        language_detection = detect_language(text)
        declared = declared.model_copy(update={"language": language_detection["language"]})
    else:
        language_detection = {"language": declared.language, "name": declared.language,
                              "confidence": None, "status": "provided", "method": "user-declared"}
    shingles = shingle_set(text)
    near = []
    for candidate in db.scalars(select(Document)):
        meta = candidate.metadata_json or {}
        if meta.get("deleted"):
            continue
        candidate_text = _read_extracted(meta)
        other = shingle_set(candidate_text)
        union = shingles | other
        score = len(shingles & other) / len(union) if union else 0
        if score >= .5:
            near.append({"document_id": candidate.id, "filename": candidate.filename, "jaccard": round(score, 4)})
    doc_id = str(uuid.uuid4())
    folder = STORAGE / doc_id
    folder.mkdir(parents=True, exist_ok=False)
    original_path = folder / f"original{ext}"
    extracted_path = folder / "extracted.json"
    try:
        original_path.write_bytes(data)
        extracted_path.write_text(json.dumps({"pages": pages, "raw_text": text}, ensure_ascii=False), encoding="utf-8")
        stored = {"declared": declared.model_dump(mode="json"), "word_count": word_count, "quality_flags": flags,
                  "language_detection": language_detection,
                  "duplicate_flags": near, "original_path": str(original_path.relative_to(ROOT)),
                  "extracted_path": str(extracted_path.relative_to(ROOT))}
        if declared.consent:
            stored["consent_record"] = {"statement": declared.consent,
                                        "recorded_at": datetime.now(timezone.utc).isoformat()}
        doc = Document(id=doc_id, filename=filename, sha256=digest, metadata_json=stored)
        db.add(doc)
        audit(db, "DOCUMENT_CREATED", doc_id, {"sha256": digest, "filename": filename})
        db.commit()
    except Exception:
        db.rollback()
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return view(doc)


def _read_extracted(meta: dict):
    rel = meta.get("extracted_path")
    if not rel:
        return ""
    path = (ROOT / rel).resolve()
    if not path.is_relative_to(STORAGE.resolve()):
        return ""
    try:
        return json.loads(path.read_text(encoding="utf-8"))["raw_text"]
    except (OSError, ValueError, KeyError):
        return ""


@router.get("/documents")
def list_documents(q: str | None = None, provenance: str | None = None, language: str | None = None, include_deleted: bool = False, db: Session = Depends(get_db)):
    documents = db.scalars(select(Document).order_by(Document.created_at.desc())).all()
    results = []
    for doc in documents:
        row = view(doc)
        if row["deleted"] and not include_deleted:
            continue
        if q and q.lower() not in doc.filename.lower():
            continue
        if provenance and row["metadata"].get("provenance") != provenance:
            continue
        if language and row["metadata"].get("language", "").lower() != language.lower():
            continue
        results.append(row)
    return results


@router.get("/documents/manifest.csv")
def export_manifest(db: Session = Depends(get_db)):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id", "filename", "sha256", "metadata_json"])
    writer.writeheader()
    for doc in db.scalars(select(Document).order_by(Document.id)):
        writer.writerow({"id": doc.id, "filename": doc.filename, "sha256": doc.sha256, "metadata_json": json.dumps(doc.metadata_json, ensure_ascii=False, sort_keys=True)})
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=documents-manifest.csv"})


@router.post("/documents/manifest.csv")
async def import_manifest(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        rows = list(csv.DictReader(io.StringIO((await file.read()).decode("utf-8-sig"))))
        validated = []
        for row in rows:
            meta = json.loads(row["metadata_json"])
            DocumentMetadata.model_validate(meta["declared"])
            if len(row["sha256"]) != 64:
                raise ValueError("invalid SHA-256")
            original = (ROOT / meta["original_path"]).resolve()
            extracted = (ROOT / meta["extracted_path"]).resolve()
            if not original.is_relative_to(STORAGE.resolve()) or not extracted.is_relative_to(STORAGE.resolve()):
                raise ValueError("manifest paths must remain inside document storage")
            if hashlib.sha256(original.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError(f"stored original hash mismatch for {row['filename']}")
            json.loads(extracted.read_text(encoding="utf-8"))
            validated.append((row, meta))
    except (UnicodeDecodeError, csv.Error, KeyError, ValueError, OSError, ValidationError) as exc:
        raise HTTPException(422, f"Invalid document manifest: {exc}") from exc
    created = 0
    for row, meta in validated:
        existing = db.get(Document, row["id"])
        duplicate_hash = db.scalar(select(Document).where(Document.sha256 == row["sha256"]))
        if existing or (duplicate_hash and duplicate_hash.id != row["id"]):
            continue
        db.add(Document(id=row["id"], filename=row["filename"], sha256=row["sha256"], metadata_json=meta))
        audit(db, "DOCUMENT_IMPORTED", row["id"], {"sha256": row["sha256"]})
        created += 1
    db.commit()
    return {"imported": created, "rows": len(validated)}


@router.get("/documents/{document_id}/audit")
def get_document_audit(document_id: str, db: Session = Depends(get_db)):
    if not db.get(Document, document_id):
        raise HTTPException(404, "Document not found")
    events = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == document_id).order_by(AuditEvent.created_at)).all()
    return [{"event_type": event.event_type, "created_at": event.created_at.isoformat(), "details": event.details} for event in events]


@router.get("/documents/{document_id}")
def get_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc or (doc.metadata_json or {}).get("deleted"):
        raise HTTPException(404, "Document not found")
    meta = doc.metadata_json or {}
    try:
        extracted_path = (ROOT / meta["extracted_path"]).resolve()
        if not extracted_path.is_relative_to(STORAGE.resolve()):
            raise ValueError("stored path escaped document storage")
        extracted = json.loads(extracted_path.read_text(encoding="utf-8"))
    except (OSError, KeyError, ValueError) as exc:
        raise HTTPException(500, "Stored extraction is unavailable") from exc
    return {**view(doc), "pages": extracted["pages"], "original_path": meta["original_path"]}


@router.patch("/documents/{document_id}")
def update_document(document_id: str, metadata: dict, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc or (doc.metadata_json or {}).get("deleted"):
        raise HTTPException(404, "Document not found")
    try:
        declared = DocumentMetadata.model_validate(metadata)
    except ValidationError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    updated = dict(doc.metadata_json or {})
    updated["declared"] = declared.model_dump(mode="json")
    doc.metadata_json = updated
    audit(db, "DOCUMENT_UPDATED", doc.id, {"fields": sorted(metadata)})
    db.commit()
    db.refresh(doc)
    return view(doc)


@router.delete("/documents/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc or (doc.metadata_json or {}).get("deleted"):
        raise HTTPException(404, "Document not found")
    updated = dict(doc.metadata_json or {})
    updated["deleted"] = True
    doc.metadata_json = updated
    audit(db, "DOCUMENT_DELETED", doc.id, {"sha256": doc.sha256})
    db.commit()
    return {"deleted": True, "id": doc.id}
