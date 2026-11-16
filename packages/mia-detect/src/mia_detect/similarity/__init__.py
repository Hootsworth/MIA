# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
"""Readable, standalone text-similarity primitives based on winnowing."""

from .index import FingerprintIndex, SQLiteFingerprintIndex
from .matching import MatchReport, SourceMatch, check_text, index_directory
from .normalize import NormalizedText, Token, normalize_text
from .winnowing import (
    DEFAULT_K,
    DEFAULT_W,
    Fingerprint,
    Shingle,
    fingerprint_text,
    make_shingles,
    stable_hash,
    winnow,
)

__all__ = [
    "DEFAULT_K", "DEFAULT_W", "Fingerprint", "FingerprintIndex", "MatchReport",
    "NormalizedText", "SQLiteFingerprintIndex", "Shingle", "SourceMatch", "Token",
    "check_text", "fingerprint_text", "index_directory", "make_shingles",
    "normalize_text", "stable_hash", "winnow",
]
