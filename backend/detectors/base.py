from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


@dataclass(frozen=True)
class DetectorMetadata:
    key: str
    name: str
    model_id: str
    revision: str
    languages: tuple[str, ...]
    min_words: int
    max_sequence_length: int
    score_semantics: str
    training_summary: str
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class DetectorInput:
    document_id: str
    text: str
    language: str


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: tuple[str, ...] = ()
    word_count: int = 0


@dataclass(frozen=True)
class DetectionResult:
    document_id: str
    detector_id: str
    detector_version_id: str
    model_id: str
    revision: str
    configuration: dict[str, Any]
    raw_output: dict[str, Any]
    label: str
    score: float
    score_semantics: str
    duration_ms: float
    device: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HealthStatus:
    available: bool
    model_id: str
    revision: str
    device: str | None
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DetectorAdapter(Protocol):
    def metadata(self) -> DetectorMetadata: ...

    def validate(self, document: DetectorInput) -> ValidationResult: ...

    def predict(self, document: DetectorInput, detector_id: str, detector_version_id: str) -> DetectionResult: ...

    def health_check(self) -> HealthStatus: ...
