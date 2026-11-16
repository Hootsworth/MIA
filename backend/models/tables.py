# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


def new_id():
    return str(uuid.uuid4())


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class Document(Timestamped, Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)


class Dataset(Timestamped, Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    manifest: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class DatasetDocument(Timestamped, Base):
    __tablename__ = "dataset_documents"
    __table_args__ = (UniqueConstraint("dataset_id", "document_id", name="uq_dataset_document"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)


class Detector(Timestamped, Base):
    __tablename__ = "detectors"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)


class DetectorVersion(Timestamped, Base):
    __tablename__ = "detector_versions"
    __table_args__ = (UniqueConstraint("detector_id", "version", name="uq_detector_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    detector_id: Mapped[str] = mapped_column(ForeignKey("detectors.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)


class Experiment(Timestamped, Base):
    __tablename__ = "experiments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", nullable=False)
    protocol: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    interruption_reason: Mapped[str | None] = mapped_column(Text)


class ExperimentDocument(Timestamped, Base):
    __tablename__ = "experiment_documents"
    __table_args__ = (UniqueConstraint("experiment_id", "document_id", name="uq_experiment_document"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)


class Result(Timestamped, Base):
    __tablename__ = "results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    detector_version_id: Mapped[str | None] = mapped_column(ForeignKey("detector_versions.id"), nullable=True)
    output: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class TurnitinReport(Timestamped, Base):
    __tablename__ = "turnitin_reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False)
    report_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    raw_value: Mapped[str | None] = mapped_column(Text)


class HighlightedPassage(Timestamped, Base):
    __tablename__ = "highlighted_passages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    turnitin_report_id: Mapped[str] = mapped_column(ForeignKey("turnitin_reports.id", ondelete="CASCADE"), nullable=False)
    passage: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)


class AuditEvent(Timestamped, Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(36))
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class GeneratedReport(Timestamped, Base):
    __tablename__ = "generated_reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
