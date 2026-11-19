# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
"""Locally hosted ModernBERT AI-text detector."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

from backend.detectors.base import (DetectionResult, DetectorInput, DetectorMetadata,
                                    HealthStatus, ValidationResult)
from backend.detectors.chunking import sentence_windows

MODEL_ID = "jaspai/modernbert-ai-text-detector"
MODEL_REVISION = "a12cb885313fd3b44a190bb31412bc72d15c4891"
ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "storage" / "models" / "hub" / "models--jaspai--modernbert-ai-text-detector" / "snapshots" / MODEL_REVISION
MIN_WORDS = 50
MAX_TOKENS = 512


class ModernBERTDetector:
    key = "modernbert-ai-text-detector"

    def __init__(self):
        self._tokenizer = None
        self._model = None
        self._torch = None
        self._device = None
        self._load_error = None

    def metadata(self):
        return DetectorMetadata(
            key=self.key, name="ModernBERT · MAGE general detector", model_id=MODEL_ID,
            revision=MODEL_REVISION, languages=("en", "eng", "english"), min_words=MIN_WORDS,
            max_sequence_length=MAX_TOKENS, score_semantics="uncalibrated machine-class probability",
            training_summary="ModernBERT-base fine-tuned on MAGE; reported cross-dataset transfer results.",
            limitations=("English only; detects fully machine-generated documents, not reliably mixed authorship.",
                         "The model card reports weak recall on a 2025-generator probe and says thresholds need local human-text calibration.",
                         "Its output is model evidence, not proof of authorship."),
        )

    def cache_status(self):
        required = (MODEL_PATH / "config.json", MODEL_PATH / "model.safetensors", MODEL_PATH / "tokenizer.json")
        missing = [path.name for path in required if not path.is_file()]
        if missing:
            return False, f"Pinned weights are not downloaded. Run `make detector-models`; missing: {', '.join(missing)}."
        return True, None

    def validate(self, document: DetectorInput):
        errors = []
        if document.language.strip().lower() not in {"en", "eng", "english"}:
            errors.append(f"Unsupported language '{document.language}'. This detector is English-only.")
        word_count = len(document.text.split())
        if word_count < MIN_WORDS:
            errors.append(f"Text is too short: {word_count} words; at least {MIN_WORDS} are required.")
        return ValidationResult(not errors, tuple(errors), word_count)

    def _load(self):
        if self._model is not None:
            return
        available, reason = self.cache_status()
        if not available:
            raise RuntimeError(reason)
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, PreTrainedTokenizerFast
            self._torch = torch
            # This checkpoint was saved with Transformers 5's TokenizersBackend class.
            # Constructing the fast tokenizer directly keeps it loadable on the
            # project's Transformers 4.x range without importing repository code.
            self._tokenizer = PreTrainedTokenizerFast(
                tokenizer_file=str(MODEL_PATH / "tokenizer.json"),
                cls_token="[CLS]", sep_token="[SEP]", pad_token="[PAD]",
                mask_token="[MASK]", unk_token="[UNK]", model_max_length=MAX_TOKENS,
                clean_up_tokenization_spaces=True,
            )
            self._model = AutoModelForSequenceClassification.from_pretrained(
                str(MODEL_PATH), local_files_only=True, use_safetensors=True, trust_remote_code=False)
            self._model.eval()
            self._device = "mps" if torch.backends.mps.is_available() else "cpu"
            self._model.to(self._device)
            self._load_error = None
        except Exception as exc:
            self._load_error = str(exc)
            raise RuntimeError(f"Could not load {MODEL_ID}@{MODEL_REVISION}: {exc}") from exc

    def _classify(self, text: str):
        windows = sentence_windows(text, self._tokenizer, MAX_TOKENS - 2)
        if not windows:
            raise ValueError("No tokens could be extracted from this document.")
        labels = self._model.config.id2label
        def class_name(index):
            label = str(labels.get(str(index), labels.get(index, f"LABEL_{index}")))
            if label.casefold() == f"label_{index}" and len(labels) == 2:
                return "human" if index == 0 else "machine"
            return label
        results = []
        for chunk, token_count in windows:
            batch = self._tokenizer(chunk, truncation=True, max_length=MAX_TOKENS,
                                    return_tensors="pt", add_special_tokens=True)
            batch = {key: value.to(self._device) for key, value in batch.items()}
            with self._torch.inference_mode():
                logits = self._model(**batch).logits[0]
                probabilities = self._torch.softmax(logits, dim=-1).detach().cpu().tolist()
            results.append((max(token_count, 1), probabilities,
                            {class_name(i): value for i, value in enumerate(probabilities)}))
        total = sum(weight for weight, _, _ in results)
        probabilities = [sum(weight * probs[i] for weight, probs, _ in results) / total
                         for i in range(len(results[0][1]))]
        labels = self._model.config.id2label
        distribution = {class_name(i): value for i, value in enumerate(probabilities)}
        positive_index = next((i for i in range(len(probabilities))
                               if str(labels.get(str(i), labels.get(i, ""))).casefold() in {"machine", "ai", "fake"}), 1)
        class_index = max(range(len(probabilities)), key=probabilities.__getitem__)
        label = class_name(class_index)
        return label, probabilities[positive_index], distribution, len(windows), total

    def predict(self, document: DetectorInput, detector_id: str, detector_version_id: str):
        self._load()
        started = perf_counter()
        label, machine_score, distribution, chunk_count, token_count = self._classify(document.text)
        return DetectionResult(
            document_id=document.document_id, detector_id=detector_id,
            detector_version_id=detector_version_id, model_id=MODEL_ID, revision=MODEL_REVISION,
            configuration={"max_tokens_per_chunk": MAX_TOKENS, "aggregation": "token-weighted mean"},
            raw_output={"probabilities": distribution, "chunk_count": chunk_count, "token_count": token_count},
            label=label, score=float(machine_score), score_semantics="uncalibrated machine-class probability",
            duration_ms=(perf_counter() - started) * 1000, device=self._device,
        )

    def health_check(self):
        try:
            self._load()
            self._classify("This diagnostic text confirms that the detector can tokenize and classify English writing. It is not benchmark data and has no authorship label.")
            return HealthStatus(True, MODEL_ID, MODEL_REVISION, self._device)
        except Exception as exc:
            return HealthStatus(False, MODEL_ID, MODEL_REVISION, self._device, failure_reason=str(exc))
