"""
SQLAlchemy async database models for the TDO platform.
Matches the PostgreSQL schema from tdo_build_prompt_v2.md.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    ARRAY,
    TIMESTAMP,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(Text, nullable=False)
    portal_id = Column(Text, nullable=False)
    current_version_id = Column(UUID(as_uuid=True), ForeignKey("dataset_versions.id"), nullable=True)
    resource_type = Column(Text, nullable=False, default="dataset")
    title = Column(Text, nullable=False)
    description = Column(Text)
    publisher = Column(Text, nullable=False)
    publisher_type = Column(Text, nullable=False)
    source_portal = Column(Text)
    dataset_url = Column(Text)
    keywords = Column(ARRAY(Text))
    themes = Column(ARRAY(Text))
    geographic_coverage = Column(ARRAY(Text))
    temporal_coverage_start = Column(Text)
    temporal_coverage_end = Column(Text)
    languages = Column(ARRAY(Text))
    update_frequency = Column(Text)
    last_updated = Column(Text)
    access_type = Column(Text, nullable=False)
    access_conditions = Column(Text)
    license = Column(Text)
    formats = Column(ARRAY(Text))
    contact_point = Column(Text)
    provenance = Column(Text)
    metadata_standard = Column(Text)
    # LLM-extracted from description text
    time_series_length = Column(Text)
    time_series_length_confidence = Column(Float)
    methodology_url = Column(Text)
    methodology_url_confidence = Column(Float)
    related_datasets = Column(ARRAY(Text))
    related_datasets_confidence = Column(Float)
    subject_classification = Column(ARRAY(Text))
    subject_classification_confidence = Column(Float)
    unit_of_measure = Column(Text)
    unit_of_measure_confidence = Column(Float)
    observation_count_estimate = Column(Integer)
    observation_count_estimate_confidence = Column(Float)

    confidence_score = Column(Float)
    completeness_score = Column(Float)
    freshness_score = Column(Float)
    link_healthy = Column(Boolean)
    ingestion_timestamp = Column(TIMESTAMP(timezone=True))
    # embedding stored as JSON list (vector extension used in real deployment)
    embedding = Column(JSONB)

    __table_args__ = (
        UniqueConstraint("source_id", "portal_id", name="uq_dataset_source_portal"),
    )

    versions = relationship(
        "DatasetVersion",
        foreign_keys="DatasetVersion.dataset_id",
        back_populates="dataset",
        lazy="select",
    )
    aliases = relationship("DatasetAlias", back_populates="dataset", lazy="select")
    processing_records = relationship("ProcessingRecord", back_populates="dataset", lazy="select")
    review_items = relationship("MetadataReviewQueue", back_populates="dataset", lazy="select")


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id"))
    version_number = Column(Integer, nullable=False)
    mvm_snapshot = Column(JSONB, nullable=False)
    pipeline_run_id = Column(UUID(as_uuid=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    dataset = relationship(
        "Dataset",
        foreign_keys=[dataset_id],
        back_populates="versions",
    )


class DatasetAlias(Base):
    __tablename__ = "dataset_aliases"

    alias_source_id = Column(Text, primary_key=True)
    portal_id = Column(Text, primary_key=True)
    canonical_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id"))
    first_seen = Column(TIMESTAMP(timezone=True))

    dataset = relationship("Dataset", back_populates="aliases")


class MetadataReviewQueue(Base):
    __tablename__ = "metadata_review_queue"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id"))
    pipeline_run_id = Column(UUID(as_uuid=True))
    confidence_score = Column(Float)
    field_confidence = Column(JSONB)
    field_evidence = Column(JSONB)
    review_reason = Column(Text)
    reviewed = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    dataset = relationship("Dataset", back_populates="review_items")


class ProcessingRecord(Base):
    __tablename__ = "processing_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mvm_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id"))
    raw_blob_path = Column(Text)
    raw_payload_hash = Column(Text)
    parser_version = Column(Text)
    harmoniser_version = Column(Text)
    embedding_model_version = Column(Text)
    pipeline_run_id = Column(UUID(as_uuid=True))
    field_confidence = Column(JSONB)
    field_evidence = Column(JSONB)
    llm_model_used = Column(Text)
    llm_fallback_triggered = Column(Boolean)
    flagged_for_review = Column(Boolean)
    review_reason = Column(Text)

    dataset = relationship("Dataset", back_populates="processing_records")


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portal_id = Column(Text, nullable=False)
    stage = Column(Text, nullable=False)   # harvest|detect|harmonise|embed|index
    status = Column(Text, nullable=False)  # pending|running|complete|failed
    source_id = Column(Text)
    error_message = Column(Text)
    started_at = Column(TIMESTAMP(timezone=True))
    completed_at = Column(TIMESTAMP(timezone=True))
    retry_count = Column(Integer, default=0)
