# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
from mia_detect.similarity import SQLiteFingerprintIndex

from backend.detectors import DetectorInput, registry
from backend.detectors.similarity import ALGORITHM_REVISION, SimilarityDetector


REFERENCE = "Observatory researchers compare the paths of distant stars with careful telescopes. " \
            "Their measurements reveal how gravity shapes each orbit through the changing seasons."


def test_similarity_detector_requires_a_built_reference_index(tmp_path):
    detector = SimilarityDetector(tmp_path / "not-built.sqlite3")
    available, reason = detector.resource_status()
    assert not available
    assert "Reference index not found" in reason
    assert "mia-detect index" in reason
    assert not detector.health_check().available


def test_similarity_adapter_runs_real_self_match_health_and_prediction(tmp_path):
    index_path = tmp_path / "references.sqlite3"
    index = SQLiteFingerprintIndex(index_path)
    index.add_document("reference/source.txt", "Observatory record", REFERENCE,
                       source_url="https://example.org/reference", license_name="CC BY-SA 4.0")
    detector = SimilarityDetector(index_path)
    assert detector.resource_status() == (True, None)
    health = detector.health_check()
    assert health.available
    assert health.revision == ALGORITHM_REVISION

    prediction = detector.predict(DetectorInput("query-1", REFERENCE, "en"), "detector-1", "version-1")
    result = prediction.to_dict()
    assert result["label"] is None
    assert result["score_semantics"] == "percentage"
    assert result["score"] == 100.0
    assert result["raw_output"]["sources"][0]["source_url"] == "https://example.org/reference"
    assert result["raw_output"]["sources"][0]["spans"][0]["query_text"] == REFERENCE.rstrip(".")


def test_similarity_detector_is_registered_lazily():
    fresh = type(registry)()
    assert "mia-similarity-winnowing" in fresh.keys()
    assert fresh._instances == {}
    assert isinstance(fresh.get("mia-similarity-winnowing"), SimilarityDetector)


def test_detector_registry_api_exposes_similarity_resource(client):
    response = client.get("/api/detectors")
    assert response.status_code == 200
    detectors = {item["key"]: item for item in response.json()}
    similarity = detectors["mia-similarity-winnowing"]
    assert similarity["resource_label"] == "reference index"
    assert similarity["resource_available"] is True
    assert similarity["status"] == "not_checked"


def test_similarity_validation_uses_minimum_winnowing_threshold(tmp_path):
    detector = SimilarityDetector(tmp_path / "missing.sqlite3")
    validation = detector.validate(DetectorInput("short", "just a few words here", "en"))
    assert not validation.valid
    assert validation.word_count == 5
