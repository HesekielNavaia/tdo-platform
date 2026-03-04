"""
MVM (Minimum Viable Metadata) Pydantic models for the TDO platform.
Python 3.12, Pydantic v2.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MVMRecord(BaseModel):
    # Identity
    id: str
    source_id: str
    source_id_aliases: list[str] = []
    resource_type: Literal["dataset", "table", "indicator", "collection", "unknown"] = "dataset"

    # Descriptive
    title: str
    description: str | None = None
    publisher: str
    publisher_type: Literal["NSO", "IO", "NGO", "other"]
    source_portal: str
    dataset_url: str | None = None
    keywords: list[str] = []
    themes: list[str] = []

    # Coverage
    geographic_coverage: list[str] = []
    temporal_coverage_start: str | None = None
    temporal_coverage_end: str | None = None
    languages: list[str] = []

    # Access
    update_frequency: Literal["daily", "weekly", "monthly", "annual", "irregular"] | None = None
    last_updated: str | None = None
    access_type: Literal["open", "restricted", "embargoed"]
    access_conditions: str | None = None
    license: str | None = None
    formats: list[str] = []
    contact_point: str | None = None

    # Provenance
    provenance: str | None = None
    metadata_standard: Literal["SDMX", "DCAT", "DublinCore", "DDI", "other", "unknown"]

    # Trust & quality signals
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    completeness_score: float = Field(..., ge=0.0, le=1.0)
    freshness_score: float = Field(..., ge=0.0, le=1.0)
    link_healthy: bool | None = None

    # System
    ingestion_timestamp: datetime

    @field_validator("confidence_score", "completeness_score", "freshness_score")
    @classmethod
    def validate_score_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"Score must be between 0.0 and 1.0, got {v}")
        return v


class InternalProcessingRecord(BaseModel):
    mvm_id: str

    # Auditability
    raw_blob_path: str
    raw_payload_hash: str
    parser_version: str
    harmoniser_version: str
    embedding_model_version: str
    pipeline_run_id: str

    # LLM evidence
    field_confidence: dict[str, float] = {}
    field_evidence: dict[str, str] = {}
    llm_model_used: str | None = None
    llm_fallback_triggered: bool = False

    # Review
    flagged_for_review: bool = False
    review_reason: str | None = None


class SearchFilters(BaseModel):
    geo: list[str] | None = None
    theme: list[str] | None = None
    publisher: str | None = None
    format: str | None = None
    access: Literal["open", "restricted", "embargoed"] | None = None
    resource_type: Literal["dataset", "table", "indicator", "collection", "unknown"] | None = None
    updated_after: str | None = None
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SearchResult(BaseModel):
    record: MVMRecord
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    search_channel: str | None = None  # "semantic", "keyword", or "hybrid"


class PortalHealth(BaseModel):
    portal_id: str
    status: Literal["healthy", "degraded", "unhealthy", "unknown"]
    last_crawl_at: datetime | None = None
    record_count: int = 0
    avg_confidence_score: float | None = None
    avg_completeness_score: float | None = None
    error_message: str | None = None
