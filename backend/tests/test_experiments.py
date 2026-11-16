import json
import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mia_detect.similarity import SQLiteFingerprintIndex
from backend.api import detectors as detector_api
from backend.api import documents as document_api
from backend.api import experiments as experiment_api
from backend.core.database import Base
from backend.detectors import registry
from backend.detectors.similarity import SimilarityDetector
from backend.main import app
from backend.models import Document, Experiment, Result
from backend.services import experiment_runner


REFERENCE = (
    "Astronomers carefully compare distant galaxies through powerful telescopes. "
    "Repeated observations reveal how stellar populations change over long periods. "
    "Their measurements support a clearer account of cosmic structure and motion."
)


@pytest.fixture
def experiment_client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'experiments.db'}")
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def enable_fk(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    storage = tmp_path / "storage" / "documents"
    monkeypatch.setattr(detector_api, "SessionLocal", sessions)
    monkeypatch.setattr(document_api, "SessionLocal", sessions)
    monkeypatch.setattr(document_api, "STORAGE", storage)
    monkeypatch.setattr(document_api, "ROOT", tmp_path)
    monkeypatch.setattr(experiment_api, "ROOT", tmp_path)
    monkeypatch.setattr(experiment_api, "DOCUMENT_STORAGE", storage)
    monkeypatch.setattr(experiment_runner, "ROOT", tmp_path)
    monkeypatch.setattr(experiment_runner, "DOCUMENT_STORAGE", storage)
    monkeypatch.setattr(experiment_runner, "SessionLocal", sessions)

    index = SQLiteFingerprintIndex(tmp_path / "reference.sqlite3")
    index.add_document("source-1", "Astronomy source", REFERENCE)
    adapter = SimilarityDetector(tmp_path / "reference.sqlite3")
    monkeypatch.setitem(registry._instances, "mia-similarity-winnowing", adapter)
    with TestClient(app) as client:
        yield client, sessions, storage
    engine.dispose()


def upload(client, filename: str, text: str) -> str:
    metadata = {"provenance": "HUMAN", "language": "en", "author_language_background": "UNKNOWN",
                "source": "test fixture", "license": "CC0"}
    response = client.post("/api/documents", files={"file": (filename, text.encode())},
                           data={"metadata": json.dumps(metadata)})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def payload(document_ids: list[str]) -> dict:
    return {"name": "Experiment test", "research_question": "RQ1", "hypothesis": "Exact overlap is reproducible.",
            "document_ids": document_ids, "detector_keys": ["mia-similarity-winnowing"],
            "classification_rule": "Record exact overlap percentage; do not infer authorship.",
            "metrics": ["AUROC"], "conditions": {"transformations": []}, "seed": 17}


def wait_for(client, experiment_id: str, terminal: set[str], timeout: float = 10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/experiments/{experiment_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in terminal:
            return body
        time.sleep(0.02)
    raise AssertionError(f"Experiment {experiment_id} did not reach {terminal}")


def test_classification_rule_is_required(experiment_client):
    client, _, _ = experiment_client
    body = payload(["document-id"])
    del body["classification_rule"]
    assert client.post("/api/experiments", json=body).status_code == 422


def test_analysis_requires_structured_rule_and_is_honest_about_one_class(experiment_client):
    client, sessions, _ = experiment_client
    document_id = upload(client, "one-class.txt", REFERENCE)
    with sessions() as db:
        legacy = Experiment(name="legacy", status="COMPLETED", protocol={"classification_rule": "free text", "metrics": ["auroc"]})
        db.add(legacy); db.commit(); db.refresh(legacy)
        legacy_id = legacy.id
        current = Experiment(name="one class", status="COMPLETED", protocol={
            "protocol_version": "m6.1", "seed": 3, "metrics": ["auroc"],
            "classification_rule": {"version": "m6.1", "positive_provenance": ["AI_GENERATED"],
                "negative_provenance": ["HUMAN"], "detectors": {"fixture": {"direction": "higher", "threshold": 50}}},
            "document_snapshot": [{"id": document_id, "provenance": "HUMAN", "source_group": "fixture"}],
            "detector_snapshot": [{"key": "fixture", "version_id": None, "score_semantics": "percentage"}],
        })
        db.add(current); db.commit(); db.refresh(current)
        current_id = current.id
        db.add(Result(experiment_id=current_id, document_id=document_id, detector_version_id=None,
                      output={"score": 20.0, "score_semantics": "percentage"}))
        db.commit()
    assert client.get(f"/api/analysis/experiments/{legacy_id}").status_code == 422
    response = client.get(f"/api/analysis/experiments/{current_id}")
    assert response.status_code == 200, response.text
    item = response.json()["detectors"][0]
    assert item["n"] == 1 and item["metrics"]["auroc"] is None
    assert item["insufficient_classes"] is True


def test_snapshot_is_frozen_and_duplicate_creates_draft(experiment_client):
    client, _, _ = experiment_client
    document_id = upload(client, "astronomy.txt", REFERENCE)
    assert client.post("/api/detectors/mia-similarity-winnowing/health").status_code == 200
    created = client.post("/api/experiments", json=payload([document_id]))
    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["status"] == "DRAFT"
    assert draft["protocol"]["document_snapshot"][0]["sha256"]
    assert draft["protocol"]["detector_snapshot"][0]["revision"] == "k5-w4-blake2b64-v1"

    run = client.post(f"/api/experiments/{draft['id']}/run")
    assert run.status_code == 202, run.text
    finished = wait_for(client, draft["id"], {"COMPLETED", "PARTIALLY_COMPLETED"})
    assert finished["status"] == "COMPLETED"
    assert finished["progress"] == {"completed": 1, "total": 1, "failures": 0}
    assert finished["results"][0]["output"]["score"] == 100.0
    assert client.patch(f"/api/experiments/{draft['id']}", json=payload([document_id])).status_code == 409

    duplicate = client.post(f"/api/experiments/{draft['id']}/duplicate")
    assert duplicate.status_code == 201
    assert duplicate.json()["status"] == "DRAFT"
    assert duplicate.json()["protocol"] == draft["protocol"]
    assert client.post(f"/api/experiments/{duplicate.json()['id']}/run").status_code == 202
    replay = wait_for(client, duplicate.json()["id"], {"COMPLETED"})
    assert replay["results"][0]["output"]["score"] == finished["results"][0]["output"]["score"]
    assert replay["results"][0]["output"]["raw_output"] == finished["results"][0]["output"]["raw_output"]


def test_resume_retries_failed_pair_and_preserves_successful_pair(experiment_client):
    client, sessions, storage = experiment_client
    first = upload(client, "first.txt", REFERENCE)
    second = upload(client, "second.txt", "Separate writing discusses ancient maps and coastal settlements in detail.")
    assert client.post("/api/detectors/mia-similarity-winnowing/health").status_code == 200
    created = client.post("/api/experiments", json=payload([first, second]))
    assert created.status_code == 201, created.text

    with sessions() as db:
        document = db.get(Document, second)
        extracted_path = storage.parent.parent / document.metadata_json["extracted_path"]
    stored = json.loads(extracted_path.read_text())
    stored["raw_text"] += " Tampered after snapshot."
    extracted_path.write_text(json.dumps(stored))

    response = client.post(f"/api/experiments/{created.json()['id']}/run")
    assert response.status_code == 202
    partial = wait_for(client, created.json()["id"], {"PARTIALLY_COMPLETED"})
    assert partial["progress"] == {"completed": 2, "total": 2, "failures": 1}
    first_result_id = next(row["id"] for row in partial["results"] if row["document_id"] == first)

    with sessions() as db:
        experiment = db.get(Experiment, created.json()["id"])
        assert experiment.status == "PARTIALLY_COMPLETED"

    # Restore the immutable extraction snapshot; resume retries only the failed pair.
    with sessions() as db:
        doc = db.get(Document, second)
        expected_path = storage.parent.parent / doc.metadata_json["extracted_path"]
    restored = json.loads(expected_path.read_text())
    restored["raw_text"] = "Separate writing discusses ancient maps and coastal settlements in detail."
    expected_path.write_text(json.dumps(restored))

    resumed = client.post(f"/api/experiments/{created.json()['id']}/resume")
    assert resumed.status_code == 202, resumed.text
    complete = wait_for(client, created.json()["id"], {"COMPLETED"})
    assert complete["progress"] == {"completed": 2, "total": 2, "failures": 0}
    assert len(complete["results"]) == 2
    assert next(row["id"] for row in complete["results"] if row["document_id"] == first) == first_result_id


def test_restart_marks_running_experiment_partial_and_resumable(experiment_client):
    client, sessions, _ = experiment_client
    document_id = upload(client, "restart.txt", REFERENCE)
    assert client.post("/api/detectors/mia-similarity-winnowing/health").status_code == 200
    created = client.post("/api/experiments", json=payload([document_id])).json()
    with sessions() as db:
        experiment = db.get(Experiment, created["id"])
        experiment.status = "RUNNING"
        experiment.total_items = 1
        experiment.completed_items = 0
        db.commit()

    experiment_runner.recover_interrupted_experiments()
    interrupted = client.get(f"/api/experiments/{created['id']}").json()
    assert interrupted["status"] == "PARTIALLY_COMPLETED"
    assert "Backend stopped" in interrupted["interruption_reason"]

    resumed = client.post(f"/api/experiments/{created['id']}/resume")
    assert resumed.status_code == 202
    complete = wait_for(client, created["id"], {"COMPLETED"})
    assert complete["progress"] == {"completed": 1, "total": 1, "failures": 0}


def test_cancel_between_items_stops_additional_results(experiment_client, monkeypatch):
    client, _, _ = experiment_client
    first = upload(client, "cancel-first.txt", REFERENCE)
    second = upload(client, "cancel-second.txt", "A separate archive records coastal trade and historic navigation routes.")
    assert client.post("/api/detectors/mia-similarity-winnowing/health").status_code == 200
    created = client.post("/api/experiments", json=payload([first, second])).json()

    entered_pair = threading.Event()
    allow_pair = threading.Event()
    original = experiment_runner._record_pair

    def pause_before_real_pair(*args):
        entered_pair.set()
        assert allow_pair.wait(5), "test did not release the in-flight pair"
        original(*args)

    monkeypatch.setattr(experiment_runner, "_record_pair", pause_before_real_pair)
    assert client.post(f"/api/experiments/{created['id']}/run").status_code == 202
    assert entered_pair.wait(5), "worker did not begin its first pair"
    cancel = client.post(f"/api/experiments/{created['id']}/cancel")
    assert cancel.status_code == 202
    allow_pair.set()
    cancelled = wait_for(client, created["id"], {"CANCELLED"})
    assert cancelled["progress"]["completed"] == 1
    assert len(cancelled["results"]) == 1
