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

    # ── Extended Provenance (DCAT-AP 2.1, Dublin Core, W3C PROV) ─────────────
    version = Column(Text)
    version_notes = Column(Text)
    derived_from = Column(ARRAY(Text))
    supersedes = Column(ARRAY(Text))
    is_part_of = Column(Text)
    source_system = Column(Text)
    processing_steps = Column(ARRAY(Text))
    source_metadata_url = Column(Text)
    data_collection_start = Column(Text)
    data_collection_end = Column(Text)
    issued = Column(Text)
    modified = Column(Text)
    license_uri = Column(Text)
    contact_email = Column(Text)

    # ── Access & Endpoints (DCAT-AP 2.1, VoID, OGC) ──────────────────────────
    api_endpoint = Column(Text)
    api_documentation_url = Column(Text)
    sparql_endpoint = Column(Text)
    bulk_download_url = Column(Text)
    wfs_endpoint = Column(Text)
    wcs_endpoint = Column(Text)
    odata_endpoint = Column(Text)
    download_urls = Column(ARRAY(Text))
    media_types = Column(ARRAY(Text))

    # ── Statistical Methodology (SDMX 3.0, DDI-CDI) ──────────────────────────
    statistical_unit = Column(Text)
    statistical_unit_confidence = Column(Float)
    statistical_population = Column(Text)
    collection_mode = Column(Text)
    imputation_method = Column(Text)
    seasonal_adjustment = Column(Text)
    classification_systems = Column(ARRAY(Text))
    classification_systems_confidence = Column(Float)
    reference_period = Column(Text)
    reference_period_confidence = Column(Float)
    revision_policy = Column(Text)
    coverage_rate = Column(Text)
    sample_size = Column(Text)
    confidentiality_policy = Column(Text)
    embargo_date = Column(Text)

    # ── Data Quality (ISO 19115, DCAT-AP 2.1, DataCite) ──────────────────────
    accuracy_notes = Column(Text)
    completeness_notes = Column(Text)
    consistency_notes = Column(Text)
    validation_report_url = Column(Text)
    known_issues = Column(Text)
    quality_assurance_procedure = Column(Text)

    # ── Geographic Metadata (ISO 19115, DCAT-AP 2.1) ─────────────────────────
    spatial_resolution = Column(Text)
    coordinate_system = Column(Text)
    bounding_box = Column(Text)
    geographic_level = Column(Text)

    # ── Interoperability (SDMX, Eurostat, Wikidata, VoID) ────────────────────
    concept_uris = Column(ARRAY(Text))
    related_standards = Column(ARRAY(Text))
    wikidata_id = Column(Text)
    eurostat_code = Column(Text)
    sdmx_dataflow_id = Column(Text)
    sdmx_agency_id = Column(Text)
    dsd_url = Column(Text)
    linked_data_uri = Column(Text)

    # ── FAIR Principles ───────────────────────────────────────────────────────
    persistent_identifier = Column(Text)
    metadata_standard_uri = Column(Text)
    vocabulary_uris = Column(ARRAY(Text))
    reuse_conditions = Column(Text)
    rights_statement = Column(Text)

    # ── Citation (DataCite 4.4) ────────────────────────────────────────────────
    doi = Column(Text)
    isbn = Column(Text)
    citation_text = Column(Text)
    preferred_citation_format = Column(Text)
    publication_year = Column(Integer)
    creators = Column(ARRAY(Text))
    contributors = Column(ARRAY(Text))
    funding_info = Column(ARRAY(Text))
    related_identifiers = Column(ARRAY(Text))

    # ── Dublin Core extensions ────────────────────────────────────────────────
    dc_type = Column(Text)
    dc_subject = Column(ARRAY(Text))
    dc_relation = Column(ARRAY(Text))
    dc_rights = Column(Text)
    dc_format = Column(Text)
    dc_audience = Column(ARRAY(Text))
    dc_accrual_periodicity = Column(Text)
    dc_conforms_to = Column(ARRAY(Text))

    # ── AI & ML Usability (Croissant ML, schema.org/Dataset) ─────────────────
    query_hints = Column(ARRAY(Text))
    query_hints_confidence = Column(Float)
    typical_use_cases = Column(ARRAY(Text))
    typical_use_cases_confidence = Column(Float)
    not_suitable_for = Column(ARRAY(Text))
    training_data_suitability = Column(Text)
    ml_task_types = Column(ARRAY(Text))
    croissant_url = Column(Text)

    # ── LLM-extracted from description text ───────────────────────────────────
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
