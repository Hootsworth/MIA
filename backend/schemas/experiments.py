import math
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ResearchQuestion = Literal["RQ1", "RQ2", "RQ3", "RQ4", "RQ5"]


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    research_question: ResearchQuestion
    hypothesis: str = Field(min_length=1, max_length=4000)
    document_ids: list[str] = Field(min_length=1)
    detector_keys: list[str] = Field(min_length=1)
    classification_rule: str | dict[str, Any] = Field(min_length=1, max_length=1000)
    metrics: list[str] = Field(default_factory=list)
    conditions: dict[str, Any] = Field(default_factory=dict)
    seed: int = 0
    protocol_version: str = "m5.1"

    @field_validator("name", "hypothesis")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field must not be blank")
        return value

    @field_validator("classification_rule")
    @classmethod
    def validate_rule(cls, value):
        if isinstance(value, str):
            if not value.strip():
                raise ValueError("This field must not be blank")
            return value.strip()
        if not isinstance(value, dict) or value.get("version") != "m6.1":
            raise ValueError("structured classification rules must use version m6.1")
        positive, negative = value.get("positive_provenance", []), value.get("negative_provenance", [])
        valid = {"HUMAN", "AI_GENERATED", "AI_ASSISTED"}
        if not positive or not negative or set(positive) & set(negative) or not (set(positive) | set(negative)) <= valid:
            raise ValueError("positive and negative provenance sets must be non-empty, valid, and disjoint")
        detectors = value.get("detectors")
        if not isinstance(detectors, dict) or not detectors:
            raise ValueError("structured rules must define at least one detector rule")
        for key, rule in detectors.items():
            if not isinstance(rule, dict) or rule.get("direction") not in {"higher", "lower"}:
                raise ValueError(f"detector {key} needs a higher/lower score direction")
            if "threshold" in rule and rule["threshold"] is not None:
                threshold = rule["threshold"]
                if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold):
                    raise ValueError(f"detector {key} threshold must be a finite number")
        return value

    @model_validator(mode="after")
    def validate_m6_protocol(self):
        if isinstance(self.classification_rule, dict):
            if set(self.classification_rule["detectors"]) != set(self.detector_keys):
                raise ValueError("structured classification rules must define exactly the selected detector keys")
            supported = {"accuracy", "precision", "recall", "specificity", "f1", "fpr", "fnr", "auroc", "auprc",
                         "cohen_kappa", "confusion_matrix", "calibration", "ece"}
            if not self.metrics or set(self.metrics) - supported:
                raise ValueError("m6.1 protocols must select one or more supported metric IDs")
        return self

    @field_validator("document_ids", "detector_keys")
    @classmethod
    def require_unique_values(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Duplicate IDs and detector keys are not allowed")
        return values
