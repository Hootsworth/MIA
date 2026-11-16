from enum import StrEnum
from pydantic import BaseModel, ConfigDict, model_validator


class Provenance(StrEnum):
    HUMAN = "HUMAN"
    AI_GENERATED = "AI_GENERATED"
    AI_ASSISTED = "AI_ASSISTED"


class DocumentMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provenance: Provenance
    domain: str | None = None
    genre: str | None = None
    language: str
    author_language_background: str
    source: str | None = None
    license: str | None = None
    consent: str | None = None
    generator_model: str | None = None
    generator_version: str | None = None
    prompt_reference: str | None = None
    editing_history: str | None = None

    @model_validator(mode="after")
    def require_declared_provenance(self):
        if not self.language.strip():
            raise ValueError("language must be non-empty")
        if self.provenance == Provenance.HUMAN:
            if not self.source or not self.source.strip() or not ((self.license and self.license.strip()) or (self.consent and self.consent.strip())):
                raise ValueError("HUMAN documents require source and a license or consent record")
        elif self.provenance == Provenance.AI_GENERATED:
            if not all((value and value.strip() for value in (self.generator_model, self.generator_version, self.prompt_reference))):
                raise ValueError("AI_GENERATED documents require generator_model, generator_version, and prompt_reference")
        else:
            if not all((value and value.strip() for value in (self.generator_model, self.generator_version, self.editing_history))):
                raise ValueError("AI_ASSISTED documents require generator_model, generator_version, and editing_history")
        if self.author_language_background not in {"NATIVE", "NON_NATIVE", "UNKNOWN"}:
            raise ValueError("author_language_background must be NATIVE, NON_NATIVE, or UNKNOWN")
        return self
