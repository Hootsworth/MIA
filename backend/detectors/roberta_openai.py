"""Real inference adapter for OpenAI's GPT-2-output RoBERTa detector."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

from backend.detectors.base import (  # noqa: E402
    DetectionResult,
    DetectorInput,
    DetectorMetadata,
    HealthStatus,
    ValidationResult,
)

logger = logging.getLogger(__name__)
MODEL_ID = "openai-community/roberta-base-openai-detector"
MODEL_REVISION = "6cba99c003b711c7fe94f8a3aa2be35a792cb6fa"
MIN_WORDS = 50
MAX_SEQUENCE_LENGTH = 512
HEALTH_TEXT = (
    "This short internal diagnostic passage exists only to confirm that the loaded classifier "
    "can tokenize text and return real model probabilities. It is not a benchmark example, "
    "does not carry a human or generated authorship label, and its output must never be "
    "interpreted as an evaluation result. The detector was trained on GPT-2 outputs and "
    "its score is only the model's own probability for its Fake class."
)


class DetectorInputError(ValueError):
    """The document is outside the declared limits of this adapter."""


class ModelUnavailableError(RuntimeError):
    """Weights or inference dependencies could not be loaded."""


class RobertaOpenAIDetector:
    key = "roberta-openai"

    def __init__(self):
        self._tokenizer = None
        self._model = None
        self._torch = None
        self._device: str | None = None
        self._load_error: str | None = None

    def metadata(self) -> DetectorMetadata:
        return DetectorMetadata(
            key=self.key,
            name="RoBERTa OpenAI Detector (base)",
            model_id=MODEL_ID,
            revision=MODEL_REVISION,
            languages=("en", "eng", "english"),
            min_words=MIN_WORDS,
            max_sequence_length=MAX_SEQUENCE_LENGTH,
            score_semantics="probability",
            training_summary="Fine-tuned to distinguish GPT-2 1.5B outputs from WebText.",
            limitations=(
                "English only; the training target was GPT-2, not current ChatGPT models.",
                "Scores are model probabilities, not calibrated truth or proof of authorship.",
                "Short text and non-native English writing can be misclassified.",
            ),
        )

    def validate(self, document: DetectorInput) -> ValidationResult:
        errors: list[str] = []
        words = len(document.text.split())
        language = document.language.strip().lower()
        if language not in self.metadata().languages:
            errors.append(f"Unsupported language '{document.language}'. This detector supports English only.")
        if words < MIN_WORDS:
            errors.append(f"Text is too short: {words} words; at least {MIN_WORDS} are required.")
        if not document.text.strip():
            errors.append("Document contains no text.")
        return ValidationResult(valid=not errors, errors=tuple(errors), word_count=words)

    def _cache_snapshot(self) -> Path:
        cache_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
        snapshot = cache_home / "hub" / "models--openai-community--roberta-base-openai-detector" / "snapshots" / MODEL_REVISION
        required = ("config.json", "model.safetensors", "tokenizer.json", "vocab.json", "merges.txt")
        missing = [name for name in required if not (snapshot / name).is_file()]
        if missing:
            raise ModelUnavailableError(
                f"Pinned model weights are not cached at {snapshot}; missing: {', '.join(missing)}. "
                "Run the detector health check with network access to download and verify this revision."
            )
        return snapshot

    def cache_status(self) -> tuple[bool, str | None]:
        try:
            self._cache_snapshot()
        except ModelUnavailableError as exc:
            return False, str(exc)
        return True, None

    def _load(self, force_device: str | None = None) -> None:
        if self._model is not None and self._tokenizer is not None:
            if force_device is None or self._device == force_device:
                return
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except Exception as exc:
            raise ModelUnavailableError(f"Detector dependency import failed: {exc}") from exc

        self._torch = torch
        try:
            if self._tokenizer is None:
                self._tokenizer = AutoTokenizer.from_pretrained(
                    MODEL_ID,
                    revision=MODEL_REVISION,
                    use_fast=True,
                    trust_remote_code=False,
                )
            if self._model is None:
                self._model = AutoModelForSequenceClassification.from_pretrained(
                    MODEL_ID,
                    revision=MODEL_REVISION,
                    use_safetensors=True,
                    trust_remote_code=False,
                )
                self._model.eval()
            if force_device is not None:
                device = force_device
            elif torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
            self._model.to(device)
            self._device = device
            labels = self._labels()
            if not any(label.casefold() == "fake" for label in labels):
                raise ModelUnavailableError(f"Pinned model has no Fake label; model labels are {labels!r}.")
            logger.info("Loaded %s at revision %s on %s", MODEL_ID, MODEL_REVISION, device)
        except Exception as exc:
            self._load_error = str(exc)
            raise ModelUnavailableError(f"Could not load {MODEL_ID}@{MODEL_REVISION}: {exc}") from exc

    def _labels(self) -> list[str]:
        label_map = self._model.config.id2label
        return [str(label_map[index]) for index in range(len(label_map))]

    def _token_chunks(self, text: str) -> list[dict[str, Any]]:
        tokenizer = self._tokenizer
        token_ids = tokenizer.encode(text, add_special_tokens=False)
        special_tokens = tokenizer.num_special_tokens_to_add(pair=False)
        maximum = min(MAX_SEQUENCE_LENGTH, int(self._model.config.max_position_embeddings) - 2)
        content_window = maximum - special_tokens
        if content_window <= 0:
            raise ModelUnavailableError("Tokenizer has no room for content inside the configured sequence length.")
        chunks = []
        for start in range(0, len(token_ids), content_window):
            content = token_ids[start : start + content_window]
            encoded = tokenizer.prepare_for_model(
                content,
                add_special_tokens=True,
                return_attention_mask=True,
                return_tensors="pt",
                truncation=False,
            )
            # prepare_for_model yields one unbatched sequence; the model expects
            # tensors shaped [batch, sequence].
            encoded = {key: value.unsqueeze(0) for key, value in encoded.items()}
            chunks.append({"start": start, "end": start + len(content), "encoded": encoded})
        return chunks

    def _infer(self, text: str) -> dict[str, Any]:
        self._load()
        torch = self._torch
        labels = self._labels()
        fake_index = next(index for index, label in enumerate(labels) if label.casefold() == "fake")
        chunks = self._token_chunks(text)
        outputs: list[dict[str, Any]] = []
        for chunk in chunks:
            inputs = {key: value.to(self._device) for key, value in chunk["encoded"].items()}
            with torch.inference_mode():
                logits = self._model(**inputs).logits
                probabilities = torch.softmax(logits, dim=-1)[0].detach().cpu().tolist()
            outputs.append({
                "token_start": chunk["start"],
                "token_end": chunk["end"],
                "label": labels[max(range(len(probabilities)), key=probabilities.__getitem__)],
                "probabilities": {labels[index]: float(probability) for index, probability in enumerate(probabilities)},
                "fake_probability": float(probabilities[fake_index]),
            })
        means = [sum(item["probabilities"][label] for item in outputs) / len(outputs) for label in labels]
        final_label = labels[max(range(len(means)), key=means.__getitem__)]
        return {
            "label": final_label,
            "score": float(sum(item["fake_probability"] for item in outputs) / len(outputs)),
            "chunks": outputs,
            "chunk_count": len(outputs),
            "labels": labels,
            "device": self._device,
            "aggregation": "unweighted mean of per-chunk softmax probabilities",
            "max_sequence_length": MAX_SEQUENCE_LENGTH,
        }

    def predict(self, document: DetectorInput, detector_id: str, detector_version_id: str) -> DetectionResult:
        validation = self.validate(document)
        if not validation.valid:
            raise DetectorInputError(" ".join(validation.errors))
        started = time.perf_counter()
        try:
            output = self._infer(document.text)
        except Exception as exc:
            if self._device == "mps":
                logger.warning("MPS inference failed; retrying the full document on CPU: %s", exc)
                try:
                    self._load(force_device="cpu")
                    output = self._infer(document.text)
                except Exception as cpu_exc:
                    raise ModelUnavailableError(f"MPS inference failed ({exc}); CPU retry failed ({cpu_exc}).") from cpu_exc
            else:
                raise
        duration_ms = (time.perf_counter() - started) * 1000
        return DetectionResult(
            document_id=document.document_id,
            detector_id=detector_id,
            detector_version_id=detector_version_id,
            model_id=MODEL_ID,
            revision=MODEL_REVISION,
            configuration={
                "chunking": "consecutive non-overlapping model-token windows",
                "minimum_words": MIN_WORDS,
                "max_sequence_length": MAX_SEQUENCE_LENGTH,
                "aggregation": output["aggregation"],
            },
            raw_output={"chunks": output["chunks"], "chunk_count": output["chunk_count"], "labels": output["labels"]},
            label=output["label"],
            score=output["score"],
            score_semantics="probability",
            duration_ms=duration_ms,
            device=output["device"],
        )

    def health_check(self) -> HealthStatus:
        try:
            output = self._infer(HEALTH_TEXT)
            if output["chunk_count"] < 1 or not 0 <= output["score"] <= 1:
                raise ModelUnavailableError("The model returned an invalid health-check output.")
            return HealthStatus(
                available=True,
                model_id=MODEL_ID,
                revision=MODEL_REVISION,
                device=output["device"],
            )
        except Exception as exc:
            if self._device == "mps":
                try:
                    logger.warning("MPS health inference failed; retrying on CPU: %s", exc)
                    self._load(force_device="cpu")
                    output = self._infer(HEALTH_TEXT)
                    if output["chunk_count"] < 1 or not 0 <= output["score"] <= 1:
                        raise ModelUnavailableError("The model returned an invalid CPU health-check output.")
                    return HealthStatus(
                        available=True,
                        model_id=MODEL_ID,
                        revision=MODEL_REVISION,
                        device=output["device"],
                    )
                except Exception as cpu_exc:
                    exc = ModelUnavailableError(f"MPS health inference failed ({exc}); CPU retry failed ({cpu_exc}).")
            return HealthStatus(
                available=False,
                model_id=MODEL_ID,
                revision=MODEL_REVISION,
                device=self._device,
                failure_reason=str(exc),
            )
