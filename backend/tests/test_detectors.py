# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
from backend.detectors import DetectorInput, DetectorRegistry
from backend.detectors.roberta_openai import MIN_WORDS, MODEL_REVISION, ModelUnavailableError, RobertaOpenAIDetector


def test_registry_constructs_adapters_lazily():
    registry = DetectorRegistry()
    assert registry.keys() == ("roberta-openai", "mia-similarity-winnowing")
    assert registry._instances == {}
    adapter = registry.get("roberta-openai")
    assert isinstance(adapter, RobertaOpenAIDetector)
    assert registry.get("roberta-openai") is adapter


def test_adapter_rejects_short_text_and_unsupported_language():
    adapter = RobertaOpenAIDetector()
    short = adapter.validate(DetectorInput("doc", "word " * (MIN_WORDS - 1), "en"))
    assert not short.valid
    assert any("at least 50" in error for error in short.errors)
    unsupported = adapter.validate(DetectorInput("doc", "word " * MIN_WORDS, "fr"))
    assert not unsupported.valid
    assert any("supports English only" in error for error in unsupported.errors)


def test_mps_health_failure_retries_on_cpu(monkeypatch):
    adapter = RobertaOpenAIDetector()
    adapter._device = "mps"
    calls = 0

    def infer(_text):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("MPS kernel unavailable")
        return {"chunk_count": 1, "score": 0.2, "device": "cpu"}

    monkeypatch.setattr(adapter, "_infer", infer)
    monkeypatch.setattr(adapter, "_load", lambda force_device=None: setattr(adapter, "_device", force_device))
    status = adapter.health_check()
    assert status.available
    assert status.device == "cpu"
    assert calls == 2


def test_missing_model_cache_reports_exact_unavailable_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HOME", str(tmp_path / "empty-huggingface-cache"))
    adapter = RobertaOpenAIDetector()
    cached, reason = adapter.cache_status()
    assert not cached
    assert reason is not None
    assert str(tmp_path / "empty-huggingface-cache") in reason
    assert MODEL_REVISION in reason
    try:
        adapter._cache_snapshot()
    except ModelUnavailableError as error:
        assert str(error) == reason
    else:
        raise AssertionError("Missing pinned model files should be unavailable")


def test_registry_api_exposes_cache_failure_to_ui(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HOME", str(tmp_path / "empty-huggingface-cache"))
    response = client.get("/api/detectors")
    assert response.status_code == 200
    detector = response.json()[0]
    assert detector["status"] == "unavailable"
    assert detector["weights_cached"] is False
    assert "missing: config.json" in detector["failure_reason"]
    assert MODEL_REVISION in detector["failure_reason"]
