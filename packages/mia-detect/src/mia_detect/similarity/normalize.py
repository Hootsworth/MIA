# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
"""Unicode-aware prose normalization that keeps original character offsets."""

from dataclasses import dataclass
import unicodedata


@dataclass(frozen=True)
class Token:
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class NormalizedText:
    tokens: tuple[Token, ...]

    @property
    def words(self) -> tuple[str, ...]:
        return tuple(token.text for token in self.tokens)


def _is_word_character(character: str) -> bool:
    return unicodedata.category(character)[0] in {"L", "M", "N"}


def normalize_text(text: str) -> NormalizedText:
    """Apply NFKC and case folding, discard punctuation, and preserve raw spans.

    A token's offsets cover its original spelling, even when compatibility
    normalization changes the number of Unicode code points (for example, a
    ligature). Punctuation separates words; it is not part of the token hash.
    """
    tokens: list[Token] = []
    start: int | None = None
    for position, character in enumerate(text):
        if _is_word_character(character):
            if start is None:
                start = position
        elif start is not None:
            original = text[start:position]
            normalized = unicodedata.normalize("NFKC", original).casefold()
            normalized = unicodedata.normalize("NFKC", normalized)
            if normalized:
                tokens.append(Token(normalized, start, position))
            start = None
    if start is not None:
        original = text[start:]
        normalized = unicodedata.normalize("NFKC", original).casefold()
        normalized = unicodedata.normalize("NFKC", normalized)
        if normalized:
            tokens.append(Token(normalized, start, len(text)))
    return NormalizedText(tuple(tokens))
