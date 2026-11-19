# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Callable

from backend.detectors.base import DetectorAdapter


class DetectorRegistry:
    """Construct adapters only when a caller asks for one."""

    def __init__(self):
        self._factories: dict[str, Callable[[], DetectorAdapter]] = {}
        self._instances: dict[str, DetectorAdapter] = {}
        self.register("roberta-openai", self._make_roberta)
        self.register("modernbert-ai-text-detector", self._make_modernbert)
        self.register("tropa-mini", self._make_tropa_mini)
        self.register("mia-similarity-winnowing", self._make_similarity)

    @staticmethod
    def _make_roberta():
        from backend.detectors.roberta_openai import RobertaOpenAIDetector

        return RobertaOpenAIDetector()

    @staticmethod
    def _make_similarity():
        from backend.detectors.similarity import SimilarityDetector

        return SimilarityDetector()

    @staticmethod
    def _make_modernbert():
        from backend.detectors.modernbert import ModernBERTDetector

        return ModernBERTDetector()

    @staticmethod
    def _make_tropa_mini():
        from backend.detectors.tropa_mini import TropaMiniDetector

        return TropaMiniDetector()

    def register(self, key: str, factory: Callable[[], DetectorAdapter]) -> None:
        self._factories[key] = factory

    def get(self, key: str) -> DetectorAdapter:
        if key not in self._factories:
            raise KeyError(f"Unknown detector '{key}'.")
        if key not in self._instances:
            self._instances[key] = self._factories[key]()
        return self._instances[key]

    def keys(self) -> tuple[str, ...]:
        return tuple(self._factories)


registry = DetectorRegistry()
