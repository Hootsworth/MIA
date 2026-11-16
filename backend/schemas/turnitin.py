"""Validated manual Turnitin report import payloads; no vendor API integration."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ScoreState = Literal["value", "censored_low", "not_displayed"]


class PassageAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passage: str = Field(min_length=1, max_length=10000)
    page: int | None = Field(default=None, ge=1)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def valid_range(self):
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError("passage end must be at or after start")
        return self


class TurnitinImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=36, max_length=36)
    confirmed_document_id: str = Field(min_length=36, max_length=36)
    identity_confirmed: bool
    submission_reference: str = Field(min_length=1, max_length=255)
    report_timestamp: datetime
    submitted_file_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    eligible_word_count: int = Field(ge=0)
    word_count_tolerance: int = Field(default=10, ge=0, le=10000)
    similarity_raw_value: str | None = Field(default=None, max_length=100)
    similarity_state: ScoreState = "not_displayed"
    similarity_censoring_upper_bound: float | None = Field(default=None, ge=0, le=100)
    ai_raw_value: str = Field(min_length=1, max_length=100)
    ai_state: ScoreState
    ai_censoring_upper_bound: float | None = Field(default=None, ge=0, le=100)
    detector_version: str | None = Field(default=None, max_length=255)
    passages: list[PassageAnnotation] = Field(default_factory=list, max_length=500)

    @field_validator("submission_reference", "ai_raw_value")
    @classmethod
    def required_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    @field_validator("report_timestamp")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("report_timestamp must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_identity_and_values(self):
        if self.document_id != self.confirmed_document_id:
            raise ValueError("confirmed document UUID does not match selected document UUID")
        if not self.identity_confirmed:
            raise ValueError("researcher must confirm the report belongs to the selected document")
        _parse_score(self.similarity_raw_value, self.similarity_state, "similarity")
        _parse_score(self.ai_raw_value, self.ai_state, "AI-writing", allow_blank=False)
        if self.similarity_censoring_upper_bound is not None and self.similarity_state != "censored_low":
            raise ValueError("similarity censoring bound only applies to censored_low state")
        if self.ai_censoring_upper_bound is not None and self.ai_state != "censored_low":
            raise ValueError("AI-writing censoring bound only applies to censored_low state")
        return self


def _parse_score(raw: str | None, state: ScoreState, label: str, *, allow_blank: bool = True) -> float | None:
    if state == "value":
        if raw is None or not raw.strip():
            if allow_blank:
                raise ValueError(f"{label} raw value is required when state is value")
            raise ValueError(f"{label} raw value is required when state is value")
        cleaned = raw.strip().removesuffix("%").strip()
        try:
            value = float(cleaned)
        except ValueError as exc:
            raise ValueError(f"{label} raw value must be a number from 0 to 100 when state is value") from exc
        if not 0 <= value <= 100:
            raise ValueError(f"{label} percentage must be between 0 and 100")
        return value
    if state == "censored_low" and (raw is None or not raw.strip()):
        raise ValueError(f"{label} must retain the exact censored display string")
    if state == "censored_low":
        try:
            float(raw.strip().removesuffix("%").strip())
        except ValueError:
            pass
        else:
            raise ValueError(f"{label} contains a numeric displayed value; select state value instead")
    if state == "not_displayed" and raw is not None:
        try:
            float(raw.strip().removesuffix("%").strip())
        except ValueError:
            pass
        else:
            raise ValueError(f"{label} contains a numeric displayed value; select state value instead")
    return None


def parse_score(raw: str | None, state: ScoreState, label: str) -> float | None:
    return _parse_score(raw, state, label)
