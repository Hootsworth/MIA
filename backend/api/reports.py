# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
"""Generate and serve research reports from persisted MIA experiment results."""

import hashlib
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.analysis import analyze_experiment
from backend.api.detectors import get_db
from backend.core.database import ROOT
from backend.models import AuditEvent, Document, Experiment, GeneratedReport, Result, TurnitinReport
from backend.reports.generator import git_revision, render_raw_csv, render_report

router = APIRouter(tags=["reports"])
GENERATED_STORAGE = ROOT / "storage" / "reports" / "generated"


def _view(row: GeneratedReport):
    metadata = row.metadata_json or {}
    return {
        "id": row.id,
        "experiment_id": row.experiment_id,
        "created_at": row.created_at.isoformat(),
        "markdown_sha256": metadata.get("markdown_sha256"),
        "csv_sha256": metadata.get("csv_sha256"),
        "analysis": metadata.get("analysis_summary", {}),
        "markdown_url": f"/api/reports/{row.id}/markdown",
        "csv_url": f"/api/reports/{row.id}/csv",
    }


def _stored_path(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(GENERATED_STORAGE.resolve()) or not path.is_file():
        raise HTTPException(404, "Generated report file not found")
    return path


@router.post("/experiments/{experiment_id}/reports", status_code=201)
def create_report(experiment_id: str, db: Session = Depends(get_db)):
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(404, "Experiment not found")
    if experiment.status != "COMPLETED":
        raise HTTPException(409, "Reports can only be generated for completed experiments")
    analysis = analyze_experiment(experiment_id, db=db)
    results = db.scalars(select(Result).where(Result.experiment_id == experiment_id).order_by(Result.created_at, Result.id)).all()
    docs = {item.id: item.filename for item in db.scalars(select(Document).where(Document.id.in_([
        row.get("id") for row in (experiment.protocol or {}).get("document_snapshot", [])
    ]))).all()}
    raw_rows = [{
        "id": result.id,
        "document_id": result.document_id,
        "detector_version_id": result.detector_version_id,
        "output": result.output or {},
        "error": (result.output or {}).get("error"),
        "created_at": result.created_at.isoformat(),
    } for result in results]
    # Include manually imported reports for snapshot documents as raw observations.
    snapshot_ids = list(docs)
    if snapshot_ids:
        for report in db.scalars(select(TurnitinReport).where(TurnitinReport.document_id.in_(snapshot_ids)).order_by(TurnitinReport.created_at)).all():
            ai = (report.report_data or {}).get("ai_writing", {})
            raw_rows.append({
                "id": report.id, "document_id": report.document_id, "detector_version_id": None,
                "output": {"score": ai.get("value"), "score_semantics": "percentage",
                           "score_state": ai.get("state", "missing"), "label": None,
                           "raw_display": ai.get("raw")},
                "detector": "turnitin-manual-import",
                "error": None, "created_at": report.created_at.isoformat(),
            })
    report_id = str(uuid4())
    GENERATED_STORAGE.mkdir(parents=True, exist_ok=True)
    markdown_path = GENERATED_STORAGE / f"{report_id}.md"
    csv_path = GENERATED_STORAGE / f"{report_id}.csv"
    commit_sha = git_revision(ROOT)
    markdown = render_report(experiment, analysis, commit_sha)
    # Version key lookup comes from the immutable detector snapshot, not current registry state.
    csv_text = render_raw_csv(experiment, raw_rows, (experiment.protocol or {}).get("detector_snapshot", []))
    markdown_path.write_text(markdown, encoding="utf-8")
    csv_path.write_text(csv_text, encoding="utf-8")
    markdown_relative = str(markdown_path.relative_to(ROOT))
    csv_relative = str(csv_path.relative_to(ROOT))
    row = GeneratedReport(
        id=report_id,
        experiment_id=experiment.id,
        path=markdown_relative,
        metadata_json={
            "csv_path": csv_relative,
            "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            "csv_sha256": hashlib.sha256(csv_text.encode("utf-8")).hexdigest(),
            "commit_sha": commit_sha,
            "analysis_summary": {
                "experiment_name": experiment.name,
                "detectors": [{"key": item.get("detector"), "n": item.get("n"), "metrics": item.get("metrics", {})}
                              for item in analysis.get("detectors", [])],
                "comparisons": analysis.get("comparisons", []),
            },
        },
    )
    try:
        db.add(row)
        db.add(AuditEvent(event_type="REPORT_GENERATED", entity_id=report_id,
                          details={"experiment_id": experiment.id, "markdown_sha256": row.metadata_json["markdown_sha256"],
                                   "csv_sha256": row.metadata_json["csv_sha256"]}))
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        markdown_path.unlink(missing_ok=True)
        csv_path.unlink(missing_ok=True)
        raise
    return _view(row)


@router.get("/reports")
def list_reports(db: Session = Depends(get_db)):
    rows = db.scalars(select(GeneratedReport).order_by(GeneratedReport.created_at.desc())).all()
    return [_view(row) for row in rows]


@router.get("/reports/{report_id}")
def get_report(report_id: str, db: Session = Depends(get_db)):
    row = db.get(GeneratedReport, report_id)
    if row is None:
        raise HTTPException(404, "Report not found")
    return _view(row)


@router.get("/reports/{report_id}/markdown")
def download_markdown(report_id: str, db: Session = Depends(get_db)):
    row = db.get(GeneratedReport, report_id)
    if row is None:
        raise HTTPException(404, "Report not found")
    return FileResponse(_stored_path(row.path), media_type="text/markdown", filename=f"mia-report-{report_id}.md")


@router.get("/reports/{report_id}/csv")
def download_csv(report_id: str, db: Session = Depends(get_db)):
    row = db.get(GeneratedReport, report_id)
    if row is None:
        raise HTTPException(404, "Report not found")
    csv_path = (row.metadata_json or {}).get("csv_path")
    if not csv_path:
        raise HTTPException(404, "CSV export is not available for this report")
    return FileResponse(_stored_path(csv_path), media_type="text/csv", filename=f"mia-report-{report_id}.csv")
