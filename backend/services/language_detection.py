# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
"""Local language identification for extracted document text."""

from functools import lru_cache
from importlib.metadata import version

from lingua import LanguageDetectorBuilder

MIN_CONFIDENCE = 0.65


@lru_cache(maxsize=1)
def _detector():
    return LanguageDetectorBuilder.from_all_languages().build()


def detect_language(text: str) -> dict:
    """Return a best-effort language ID; preserve uncertainty as ``und``."""
    words = text.split()
    if len(words) < 20:
        return {"language": "und", "name": "Undetermined", "confidence": None,
                "status": "insufficient_text", "method": f"Lingua {version('lingua-language-detector')}"}

    detector = _detector()
    match = detector.detect_language_of(text)
    if match is None:
        return {"language": "und", "name": "Undetermined", "confidence": None,
                "status": "uncertain", "method": f"Lingua {version('lingua-language-detector')}"}

    confidence = detector.compute_language_confidence(text, match)
    code = match.iso_code_639_1
    language = code.name.lower() if code is not None else match.iso_code_639_3.name.lower()
    certain = confidence >= MIN_CONFIDENCE
    return {
        "language": language if certain else "und",
        "name": match.name.replace("_", " ").title() if certain else "Undetermined",
        "candidate_language": language,
        "confidence": round(confidence, 4),
        "status": "detected" if certain else "uncertain",
        "method": f"Lingua {version('lingua-language-detector')}",
    }
