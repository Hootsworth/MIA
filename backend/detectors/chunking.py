# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
"""Sentence-aware token windows shared by document-level detectors."""

import re

SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")


def sentence_windows(text: str, tokenizer, max_tokens: int) -> list[tuple[str, int]]:
    """Pack sentences into bounded windows; split unusually long sentences by token."""
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]
    windows: list[tuple[str, int]] = []
    current: list[str] = []
    current_count = 0
    for sentence in sentences:
        token_ids = tokenizer.encode(sentence, add_special_tokens=False)
        if not token_ids:
            continue
        if len(token_ids) > max_tokens:
            if current:
                windows.append((" ".join(current), current_count))
                current, current_count = [], 0
            for start in range(0, len(token_ids), max_tokens):
                part = token_ids[start:start + max_tokens]
                windows.append((tokenizer.decode(part, skip_special_tokens=True), len(part)))
            continue
        if current and current_count + len(token_ids) > max_tokens:
            windows.append((" ".join(current), current_count))
            current, current_count = [], 0
        current.append(sentence)
        current_count += len(token_ids)
    if current:
        windows.append((" ".join(current), current_count))
    return windows


def evidence_windows(text: str, tokenizer, target_tokens: int, min_words: int) -> list[tuple[str, int, int, int]]:
    """Return source-aligned, sentence-aware passages for local evidence display.

    These are classifier windows, not token-level explanations. Short trailing
    passages are joined to the preceding window to avoid scoring tiny fragments.
    """
    atoms: list[tuple[int, int, int]] = []
    cursor = 0
    for boundary in SENTENCE_BOUNDARY.finditer(text):
        left, right = cursor, boundary.start()
        while left < right and text[left].isspace():
            left += 1
        while right > left and text[right - 1].isspace():
            right -= 1
        if left < right:
            atoms.extend(_token_aligned_atoms(text, left, right, tokenizer, target_tokens))
        cursor = boundary.end()
    left, right = cursor, len(text)
    while left < right and text[left].isspace():
        left += 1
    while right > left and text[right - 1].isspace():
        right -= 1
    if left < right:
        atoms.extend(_token_aligned_atoms(text, left, right, tokenizer, target_tokens))

    windows: list[tuple[int, int, int]] = []
    start = end = None
    token_count = word_count = 0
    for atom_start, atom_end, atom_tokens in atoms:
        atom_words = len(text[atom_start:atom_end].split())
        if start is not None and token_count >= target_tokens and word_count >= min_words:
            windows.append((start, end, token_count))
            start = end = None
            token_count = word_count = 0
        if start is None:
            start = atom_start
        end = atom_end
        token_count += atom_tokens
        word_count += atom_words
    if start is not None:
        if windows and word_count < min_words:
            previous_start, _, previous_tokens = windows[-1]
            windows[-1] = (previous_start, end, previous_tokens + token_count)
        else:
            windows.append((start, end, token_count))
    return [(text[start:end], start, end, tokens) for start, end, tokens in windows]


def _token_aligned_atoms(text: str, start: int, end: int, tokenizer, target_tokens: int) -> list[tuple[int, int, int]]:
    source = text[start:end]
    token_ids = tokenizer.encode(source, add_special_tokens=False)
    if len(token_ids) <= target_tokens:
        return [(start, end, len(token_ids))] if token_ids else []

    encoded = tokenizer(source, add_special_tokens=False, return_offsets_mapping=True)
    offsets = encoded["offset_mapping"]
    atoms = []
    for token_start in range(0, len(offsets), target_tokens):
        token_end = min(token_start + target_tokens, len(offsets))
        char_start = offsets[token_start][0]
        char_end = offsets[token_end - 1][1]
        if char_start < char_end:
            atoms.append((start + char_start, start + char_end, token_end - token_start))
    return atoms
