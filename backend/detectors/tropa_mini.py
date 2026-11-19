# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
"""Locally hosted four-class Tropa Mini AI-text detector."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

from backend.detectors.base import (DetectionResult, DetectorInput, DetectorMetadata,
                                    HealthStatus, ValidationResult)
from backend.detectors.chunking import evidence_windows, sentence_windows

MODEL_ID = "wasitaigeneratedcom/tropa-mini-ai-text-detector"
MODEL_REVISION = "10fecd0856ed65ddfe92b88416b0a1e1350d8fb8"
ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "storage" / "models" / "hub" / "models--wasitaigeneratedcom--tropa-mini-ai-text-detector" / "snapshots" / MODEL_REVISION
MIN_WORDS = 50
MAX_TOKENS = 512
EVIDENCE_TOKENS = 80
AI_RELATED_THRESHOLD = 0.9755912190656111
LABELS = ("human", "ai", "ai_edited", "humanized")


class TropaMiniDetector:
    key = "tropa-mini"

    def __init__(self):
        self._tokenizer = None
        self._model = None
        self._torch = None
        self._device = None
        self._load_error = None

    def metadata(self):
        return DetectorMetadata(
            key=self.key, name="Tropa Mini · four-class detector", model_id=MODEL_ID,
            revision=MODEL_REVISION, languages=("en", "eng", "english"), min_words=MIN_WORDS,
            max_sequence_length=MAX_TOKENS, score_semantics="AI-related class score (1 − P(human))",
            training_summary="DeBERTa-v3-large fine-tuned for human, AI, AI-edited, and humanized classes.",
            limitations=("English-first; performance is strongest on modern English prose.",
                         "The model card's conservative threshold is calibrated to its own held-out human set, not MIA's users.",
                         "It can misread historical, short, edited, or out-of-domain human writing; output is not proof of authorship."),
        )

    def cache_status(self):
        required = (MODEL_PATH / "config.json", MODEL_PATH / "model.safetensors",
                    MODEL_PATH / "tokenizer.json", MODEL_PATH / "serving_head.json")
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
            import torch.nn as nn
            from transformers import AutoConfig, AutoModel, AutoTokenizer, DebertaV2Config, PreTrainedModel

            class FourClassModel(PreTrainedModel):
                config_class = DebertaV2Config

                def __init__(self, config):
                    super().__init__(config)
                    self.model = AutoModel.from_config(config)
                    self.classifier = nn.Linear(config.hidden_size, config.detector_num_labels)
                    self.post_init()

                def forward(self, input_ids=None, attention_mask=None, **kwargs):
                    output = self.model(input_ids=input_ids, attention_mask=attention_mask, **kwargs)
                    hidden = output.last_hidden_state
                    mask = attention_mask.unsqueeze(-1).to(hidden.dtype)
                    pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
                    return self.classifier(pooled)

            self._torch = torch
            config = AutoConfig.from_pretrained(str(MODEL_PATH), local_files_only=True, trust_remote_code=False)
            self._tokenizer = AutoTokenizer.from_pretrained(str(MODEL_PATH), local_files_only=True, use_fast=True,
                                                            trust_remote_code=False)
            self._model = FourClassModel.from_pretrained(str(MODEL_PATH), config=config,
                                                          local_files_only=True, use_safetensors=True,
                                                          trust_remote_code=False)
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
        rows = []
        for chunk, token_count in windows:
            batch = self._tokenizer(chunk, truncation=True, max_length=MAX_TOKENS,
                                    return_tensors="pt", add_special_tokens=True)
            batch = {key: value.to(self._device) for key, value in batch.items()}
            with self._torch.inference_mode():
                logits = self._model(**batch)[0]
                probabilities = self._torch.softmax(logits, dim=-1).detach().cpu().tolist()
            rows.append((max(token_count, 1), probabilities))
        total = sum(weight for weight, _ in rows)
        probabilities = [sum(weight * values[index] for weight, values in rows) / total
                         for index in range(len(LABELS))]
        distribution = dict(zip(LABELS, probabilities))
        top_label = max(LABELS, key=distribution.__getitem__)
        ai_related_score = 1.0 - distribution["human"]
        return top_label, ai_related_score, distribution, len(windows), total

    def _passage_evidence(self, text: str):
        passages = []
        for chunk, start, end, token_count in evidence_windows(
                text, self._tokenizer, EVIDENCE_TOKENS, MIN_WORDS):
            batch = self._tokenizer(chunk, truncation=True, max_length=MAX_TOKENS,
                                    return_tensors="pt", add_special_tokens=True)
            batch = {key: value.to(self._device) for key, value in batch.items()}
            with self._torch.inference_mode():
                logits = self._model(**batch)[0]
                values = self._torch.softmax(logits, dim=-1).detach().cpu().tolist()
            distribution = dict(zip(LABELS, values))
            label = max(LABELS, key=distribution.__getitem__)
            passages.append({
                "start": start,
                "end": end,
                "label": label,
                "ai_related_score": 1.0 - distribution["human"],
                "class_probabilities": distribution,
                "token_count": token_count,
            })
        return passages

    def predict(self, document: DetectorInput, detector_id: str, detector_version_id: str):
        self._load()
        started = perf_counter()
        label, ai_related_score, distribution, chunk_count, token_count = self._classify(document.text)
        evidence_spans = self._passage_evidence(document.text)
        return DetectionResult(
            document_id=document.document_id, detector_id=detector_id,
            detector_version_id=detector_version_id, model_id=MODEL_ID, revision=MODEL_REVISION,
            configuration={"max_tokens_per_chunk": MAX_TOKENS, "aggregation": "token-weighted mean",
                           "reference_threshold": AI_RELATED_THRESHOLD,
                           "evidence_method": f"sentence-aware passages targeting {EVIDENCE_TOKENS} tokens; windows shorter than {MIN_WORDS} words are merged"},
            raw_output={"class_probabilities": distribution, "ai_related_score": ai_related_score,
                        "reference_threshold": AI_RELATED_THRESHOLD, "reference_threshold_met": ai_related_score >= AI_RELATED_THRESHOLD,
                        "threshold_note": "Model-card threshold selected on the publisher's 0.5% FPR validation set; not locally calibrated.",
                        "chunk_count": chunk_count, "token_count": token_count,
                        "evidence_spans": evidence_spans,
                        "evidence_note": "Passage classes are independent model outputs, not token-level explanations or proof of authorship."},
            label=label, score=float(ai_related_score), score_semantics="AI-related class score (1 − P(human))",
            duration_ms=(perf_counter() - started) * 1000, device=self._device,
        )

    def health_check(self):
        try:
            self._load()
            self._classify("This diagnostic English paragraph checks that the detector can tokenize and return its four real class scores. It is not evaluation data and carries no authorship label.")
            return HealthStatus(True, MODEL_ID, MODEL_REVISION, self._device)
        except Exception as exc:
            return HealthStatus(False, MODEL_ID, MODEL_REVISION, self._device, failure_reason=str(exc))
