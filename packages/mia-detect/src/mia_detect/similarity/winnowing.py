# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

"""Stable word-shingle hashing and the winnowing fingerprint algorithm."""

from collections import deque
from dataclasses import dataclass
import hashlib

from .normalize import NormalizedText, normalize_text

DEFAULT_K = 5
DEFAULT_W = 4


@dataclass(frozen=True)
class Shingle:
    value: str
    position: int
    char_start: int
    char_end: int


@dataclass(frozen=True)
class Fingerprint:
    value: str
    position: int
    shingle: str
    char_start: int
    char_end: int


def stable_hash(shingle: str) -> str:
    """Return a platform-independent 64-bit BLAKE2b digest as hex."""
    return hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).hexdigest()


def make_shingles(text: str | NormalizedText, k: int = DEFAULT_K) -> list[Shingle]:
    if k < 1:
        raise ValueError("k must be at least 1")
    normalized = normalize_text(text) if isinstance(text, str) else text
    tokens = normalized.tokens
    return [
        Shingle(
            value=" ".join(token.text for token in tokens[start : start + k]),
            position=start,
            char_start=tokens[start].start,
            char_end=tokens[start + k - 1].end,
        )
        for start in range(max(0, len(tokens) - k + 1))
    ]


def winnow(shingles: list[Shingle], w: int = DEFAULT_W) -> list[Fingerprint]:
    """Choose each rightmost minimum hash in a window of ``w`` k-grams.

    If fewer than ``w`` k-grams exist, one minimum is selected from the
    available grams. For full windows, a shared run of ``w + k - 1`` words is
    guaranteed to contain a shared fingerprint, assuming stable equal hashes.
    """
    if w < 1:
        raise ValueError("w must be at least 1")
    if not shingles:
        return []

    hashes = [stable_hash(shingle.value) for shingle in shingles]
    window_size = min(w, len(shingles))
    minima: deque[int] = deque()
    selected: list[Fingerprint] = []
    last_selected = -1
    for index, value in enumerate(hashes):
        # Popping equal values gives ties to the rightmost occurrence.
        while minima and hashes[minima[-1]] >= value:
            minima.pop()
        minima.append(index)
        first_allowed = index - window_size + 1
        while minima and minima[0] < first_allowed:
            minima.popleft()
        if index >= window_size - 1 and minima[0] != last_selected:
            position = minima[0]
            gram = shingles[position]
            selected.append(Fingerprint(value=hashes[position], position=gram.position,
                                        shingle=gram.value, char_start=gram.char_start,
                                        char_end=gram.char_end))
            last_selected = position
    return selected


def fingerprint_text(text: str | NormalizedText, k: int = DEFAULT_K, w: int = DEFAULT_W) -> list[Fingerprint]:
    return winnow(make_shingles(text, k=k), w=w)
