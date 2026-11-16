from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ResearchQuestion = Literal["RQ1", "RQ2", "RQ3", "RQ4", "RQ5"]


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    research_question: ResearchQuestion
    hypothesis: str = Field(min_length=1, max_length=4000)
    document_ids: list[str] = Field(min_length=1)
    detector_keys: list[str] = Field(min_length=1)
    classification_rule: str = Field(min_length=1, max_length=1000)
    metrics: list[str] = Field(default_factory=list)
    conditions: dict[str, Any] = Field(default_factory=dict)
    seed: int = 0
    protocol_version: str = "m5.1"

    @field_validator("name", "hypothesis", "classification_rule")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field must not be blank")
        return value

    @field_validator("document_ids", "detector_keys")
    @classmethod
    def require_unique_values(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Duplicate IDs and detector keys are not allowed")
        return values
