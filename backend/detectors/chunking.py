# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
"""Sentence-aware token windows shared by document-level detectors."""

import re


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
