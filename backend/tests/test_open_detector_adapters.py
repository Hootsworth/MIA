# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
from backend.detectors.base import DetectorInput
from backend.detectors.chunking import sentence_windows
from backend.detectors.modernbert import ModernBERTDetector
from backend.detectors.tropa_mini import TropaMiniDetector


class WordTokenizer:
    def encode(self, text, add_special_tokens=False):
        return text.split()

    def decode(self, token_ids, skip_special_tokens=True):
        return " ".join(token_ids)


def test_long_sentence_windows_respect_token_limit():
    windows = sentence_windows(" ".join(f"word{i}" for i in range(11)), WordTokenizer(), 4)
    assert [count for _, count in windows] == [4, 4, 3]
    assert all(len(text.split()) <= 4 for text, _ in windows)


def test_sentences_are_packed_without_exceeding_limit():
    windows = sentence_windows("one two. three four. five six.", WordTokenizer(), 4)
    assert windows == [("one two. three four.", 4), ("five six.", 2)]


def test_open_detectors_declare_minimum_text_and_english_scope():
    document = DetectorInput(document_id="test", text="A short text.", language="en")
    for detector in (ModernBERTDetector(), TropaMiniDetector()):
        metadata = detector.metadata()
        validation = detector.validate(document)
        assert metadata.min_words == 50
        assert "en" in metadata.languages
        assert not validation.valid
        assert validation.word_count == 3


def test_open_detectors_reject_unknown_language():
    document = DetectorInput(document_id="test", text="a word " * 60, language="fr")
    for detector in (ModernBERTDetector(), TropaMiniDetector()):
        validation = detector.validate(document)
        assert not validation.valid
        assert any("English-only" in error for error in validation.errors)
