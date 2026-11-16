import hashlib
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api import turnitin as turnitin_api
from backend.api import detectors as detector_api
from backend.api import documents as document_api
from backend.api import experiments as experiment_api
from backend.core.database import Base
from backend.main import app
from backend.models import Experiment, TurnitinReport

REFERENCE = ("Astronomers carefully compare distant galaxies through powerful telescopes. "
             "Repeated observations reveal how stellar populations change over long periods. "
             "Their measurements support a clearer account of cosmic structure and motion.")


@pytest.fixture
def turnitin_client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'turnitin-test.db'}")
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def enable_fk(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    storage = tmp_path / "storage" / "documents"
    reports = tmp_path / "storage" / "reports"
    monkeypatch.setattr(detector_api, "SessionLocal", sessions)
    monkeypatch.setattr(document_api, "SessionLocal", sessions)
    monkeypatch.setattr(document_api, "ROOT", tmp_path)
    monkeypatch.setattr(document_api, "STORAGE", storage)
    monkeypatch.setattr(experiment_api, "ROOT", tmp_path)
    monkeypatch.setattr(turnitin_api, "ROOT", tmp_path)
    monkeypatch.setattr(turnitin_api, "REPORT_STORAGE", reports)
    with TestClient(app) as client:
        yield client, sessions, reports
    engine.dispose()


def upload_research_document(client, filename="research.txt"):
    metadata = {"provenance": "HUMAN", "language": "en", "author_language_background": "UNKNOWN",
                "source": "consented test fixture", "license": "CC0"}
    response = client.post("/api/documents", files={"file": (filename, REFERENCE.encode())},
                           data={"metadata": json.dumps(metadata)})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def turnitin_payload(document_id, document_hash, word_count, **overrides):
    payload = {
        "document_id": document_id,
        "confirmed_document_id": document_id,
        "identity_confirmed": True,
        "submission_reference": "submission-001",
        "report_timestamp": datetime(2026, 10, 1, 12, 30, tzinfo=timezone.utc).isoformat(),
        "submitted_file_sha256": document_hash,
        "eligible_word_count": word_count,
        "word_count_tolerance": 10,
        "similarity_raw_value": "14%",
        "similarity_state": "value",
        "ai_raw_value": "*",
        "ai_state": "censored_low",
        "ai_censoring_upper_bound": 20,
        "detector_version": "Turnitin version as shown",
        "passages": [{"passage": "A marked excerpt", "page": 1, "start": 0, "end": 16}],
    }
    payload.update(overrides)
    return payload


def import_report(client, payload, content=b"%PDF-1.7\nreport fixture", filename="report.pdf"):
    return client.post("/api/turnitin-reports", data={"payload": json.dumps(payload)},
                       files={"file": (filename, content, "application/pdf")})


def test_valid_import_preserves_raw_censoring_hash_and_links_to_experiment(turnitin_client):
    client, sessions, reports = turnitin_client
    document_id = upload_research_document(client, "consented-research.txt")
    document = client.get(f"/api/documents/{document_id}").json()
    pdf = b"%PDF-1.7\nreport fixture with exact content"
    created = import_report(client, turnitin_payload(document_id, document["sha256"], document["word_count"]), pdf)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["ai_writing"] == {"raw": "*", "state": "censored_low", "value": None, "censoring_upper_bound": 20.0}
    assert body["similarity"]["raw"] == "14%" and body["similarity"]["value"] == 14
    assert body["report_file_sha256"] == hashlib.sha256(pdf).hexdigest()
    assert body["score_semantics"] == "percentage"
    assert body["passages"][0]["passage"] == "A marked excerpt"
    with sessions() as db:
        report = db.get(TurnitinReport, body["id"])
        assert report.raw_value == "*"
        original = reports / report.id / "original.pdf"
        assert original.read_bytes() == pdf
        experiment = Experiment(name="report result fixture", status="COMPLETED", protocol={
            "document_snapshot": [{"id": document_id, "provenance": "HUMAN"}],
        })
        db.add(experiment); db.commit(); db.refresh(experiment)
        experiment_id = experiment.id
    experiment_view = client.get(f"/api/experiments/{experiment_id}").json()
    imported_result = next(row for row in experiment_view["results"] if row["detector_name"] == "Turnitin report (manual import)")
    assert imported_result["output"]["score"] is None
    assert imported_result["output"]["turnitin"]["ai_writing"]["state"] == "censored_low"


def test_refuses_wrong_identity_hash_word_count_and_duplicate_report(turnitin_client):
    client, _, _ = turnitin_client
    document_id = upload_research_document(client, "source.txt")
    doc = client.get(f"/api/documents/{document_id}").json()
    base = turnitin_payload(document_id, doc["sha256"], doc["word_count"])
    wrong_hash = {**base, "submitted_file_sha256": "0" * 64}
    assert import_report(client, wrong_hash, b"%PDF-1.7\nwrong hash").status_code == 409
    wrong_identity = {**base, "confirmed_document_id": "00000000-0000-0000-0000-000000000000"}
    assert import_report(client, wrong_identity, b"%PDF-1.7\nwrong UUID").status_code == 422
    wrong_words = {**base, "eligible_word_count": doc["word_count"] + 100, "word_count_tolerance": 5}
    assert import_report(client, wrong_words, b"%PDF-1.7\nwrong words").status_code == 409
    content = b"%PDF-1.7\nduplicate hash fixture"
    assert import_report(client, base, content).status_code == 201
    duplicate = import_report(client, {**base, "submission_reference": "submission-002"}, content)
    assert duplicate.status_code == 409 and "already been imported" in duplicate.text


def test_censored_and_not_displayed_values_are_not_zero_and_score_ranges_validate(turnitin_client):
    client, _, _ = turnitin_client
    document_id = upload_research_document(client, "states.txt")
    doc = client.get(f"/api/documents/{document_id}").json()
    censored = turnitin_payload(document_id, doc["sha256"], doc["word_count"],
                                similarity_raw_value=None, similarity_state="not_displayed",
                                ai_raw_value="No score shown", ai_state="not_displayed", ai_censoring_upper_bound=None)
    response = import_report(client, censored, b"%PDF-1.7\nnot displayed").json()
    assert response["ai_writing"]["state"] == "not_displayed" and response["ai_writing"]["value"] is None
    assert response["similarity"]["state"] == "not_displayed" and response["similarity"]["value"] is None
    invalid = {**turnitin_payload(document_id, doc["sha256"], doc["word_count"]), "ai_raw_value": "101%", "ai_state": "value"}
    assert import_report(client, invalid, b"%PDF-1.7\nout of range").status_code == 422
    ambiguous = {**turnitin_payload(document_id, doc["sha256"], doc["word_count"]), "ai_raw_value": "14%", "ai_state": "not_displayed"}
    assert import_report(client, ambiguous, b"%PDF-1.7\nnumeric but hidden state").status_code == 422
    assert client.get(f"/api/turnitin-reports?document_id={document_id}").status_code == 200
