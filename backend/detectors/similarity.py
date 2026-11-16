# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
"""Lab adapter around the standalone mia-detect similarity package."""

from __future__ import annotations

import os
from pathlib import Path
from time import perf_counter

from mia_detect.similarity import SQLiteFingerprintIndex, check_text, normalize_text

from backend.detectors.base import (
    DetectionResult,
    DetectorInput,
    DetectorMetadata,
    HealthStatus,
    ValidationResult,
)

ALGORITHM_REVISION = "k5-w4-blake2b64-v1"
DEFAULT_INDEX = Path(__file__).resolve().parents[2] / "storage" / "similarity" / "index.sqlite3"


class SimilarityDetector:
    """Exact word-overlap detector; it does not infer authorship or plagiarism."""

    key = "mia-similarity-winnowing"

    def __init__(self, index_path: str | Path | None = None):
        value = Path(index_path or os.environ.get("MIA_SIMILARITY_INDEX", DEFAULT_INDEX))
        self.index_path = value if value.is_absolute() else Path(__file__).resolve().parents[2] / value

    def metadata(self) -> DetectorMetadata:
        return DetectorMetadata(
            key=self.key,
            name="MIA Similarity · Winnowing",
            model_id="mia-detect.similarity.winnowing",
            revision=ALGORITHM_REVISION,
            languages=("all",),
            min_words=8,
            max_sequence_length=0,
            score_semantics="percentage",
            training_summary="Deterministic exact word-shingle fingerprint matching; no trained model.",
            limitations=(
                "Matches normalized words exactly; paraphrases and synonym substitutions are not identified.",
                "Punctuation and case differences are ignored during comparison.",
                "Overlap percentage is matched query-word coverage, not a probability or plagiarism finding.",
            ),
        )

    def resource_status(self) -> tuple[bool, str | None]:
        if not self.index_path.is_file():
            return False, (
                f"Reference index not found at {self.index_path}. Build one with "
                "`mia-detect index <corpus-dir> --database <index-path>`."
            )
        try:
            index = SQLiteFingerprintIndex(self.index_path)
            count = index.document_count()
        except Exception as exc:
            return False, f"Could not open reference index at {self.index_path}: {exc}"
        if count == 0:
            return False, f"Reference index at {self.index_path} contains no documents."
        return True, None

    def validate(self, document: DetectorInput) -> ValidationResult:
        words = len(normalize_text(document.text).tokens)
        if words < self.metadata().min_words:
            return ValidationResult(False, (f"Text is too short: {words} words; at least 8 are required.",), words)
        if not document.text.strip():
            return ValidationResult(False, ("Document contains no text."), words)
        return ValidationResult(True, (), words)

    def _index(self) -> SQLiteFingerprintIndex:
        available, reason = self.resource_status()
        if not available:
            raise RuntimeError(reason or "Similarity reference index is unavailable.")
        return SQLiteFingerprintIndex(self.index_path)

    def predict(self, document: DetectorInput, detector_id: str, detector_version_id: str) -> DetectionResult:
        validation = self.validate(document)
        if not validation.valid:
            raise ValueError(" ".join(validation.errors))
        started = perf_counter()
        index = self._index()
        report = check_text(document.text, index)
        return DetectionResult(
            document_id=document.document_id,
            detector_id=detector_id,
            detector_version_id=detector_version_id,
            model_id=self.metadata().model_id,
            revision=ALGORITHM_REVISION,
            configuration={"k": report.k, "w": report.w, "guaranteed_shared_words": report.threshold_words,
                           "overlap_denominator": "distinct query words", "index_path": str(self.index_path)},
            raw_output=report.to_dict(),
            label=None,
            score=report.overall_overlap_percentage,
            score_semantics="percentage",
            duration_ms=(perf_counter() - started) * 1000,
            device="cpu",
        )

    def health_check(self) -> HealthStatus:
        try:
            index = self._index()
            candidates = [item for item in index.list_documents() if item["token_count"] >= 8]
            if not candidates:
                raise RuntimeError("Reference index has no document with at least 8 normalized words for a real health check.")
            source = index.get_document(candidates[0]["source_id"])
            report = check_text(source["text"], index)
            match = next((item for item in report.sources if item.source_id == source["source_id"]), None)
            if match is None or match.overlap_percentage != 100.0:
                raise RuntimeError("Self-match health inference did not return 100% exact query-word overlap.")
            return HealthStatus(True, self.metadata().model_id, ALGORITHM_REVISION, "cpu")
        except Exception as exc:
            return HealthStatus(False, self.metadata().model_id, ALGORITHM_REVISION, "cpu", failure_reason=str(exc))
