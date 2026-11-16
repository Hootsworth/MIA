# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
from .tables import (
    AuditEvent, Dataset, DatasetDocument, Detector, DetectorVersion, Document,
    Experiment, ExperimentDocument, GeneratedReport, HighlightedPassage, Result,
    TurnitinReport,
)
from backend.core.database import Base

__all__ = ["Base", "Document", "Dataset", "DatasetDocument", "Detector", "DetectorVersion", "Experiment", "ExperimentDocument", "Result", "TurnitinReport", "HighlightedPassage", "AuditEvent", "GeneratedReport"]
