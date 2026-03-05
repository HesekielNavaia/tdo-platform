"""
MVM (Minimum Viable Metadata) Pydantic models for the TDO platform.
Python 3.12, Pydantic v2.

Field coverage (schema v2 — all optional fields backfilled from):
  DCAT-AP 2.1 · W3C DCAT · SDMX 3.0 / SDMX-JSON 2.0 · DDI-CDI
  Dublin Core terms + refinements · ISO 19115 · DataCite 4.4
  schema.org/Dataset · FAIR principles · Croissant ML · VoID
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MVMRecord(BaseModel):
    # ── Identity ──────────────────────────────────────────────────────────────
    id: str
    source_id: str
    source_id_aliases: list[str] = []
    resource_type: Literal["dataset", "table", "indicator", "collection", "unknown"] = "dataset"

    # ── Descriptive ───────────────────────────────────────────────────────────
    title: str
    description: str | None = None
    publisher: str
    publisher_type: Literal["NSO", "IO", "NGO", "other"]
    source_portal: str
    dataset_url: str | None = None
    keywords: list[str] = []
    themes: list[str] = []

    # ── Coverage ──────────────────────────────────────────────────────────────
    geographic_coverage: list[str] = []
    temporal_coverage_start: str | None = None
    temporal_coverage_end: str | None = None
    languages: list[str] = []

    # ── Access (core) ─────────────────────────────────────────────────────────
    update_frequency: Literal[
        "daily", "weekly", "monthly", "quarterly", "annual",
        "decennial", "irregular", "continuous", "unknown",
    ] | None = None
    last_updated: str | None = None
    access_type: Literal["open", "restricted", "embargoed"]
    access_conditions: str | None = None
    license: str | None = None
    license_uri: str | None = None          # DCAT-AP: dct:license as URI
    formats: list[str] = []
    contact_point: str | None = None
    contact_email: str | None = None        # DCAT-AP 2.1: vcard:hasEmail

    # ── Provenance (core) ─────────────────────────────────────────────────────
    provenance: str | None = None
    metadata_standard: Literal[
        "SDMX", "DCAT", "DublinCore", "DDI", "ISO19115", "DataCite", "other", "unknown"
    ]

    # ── Extended Provenance (DCAT-AP 2.1, Dublin Core, W3C PROV) ─────────────
    # dct:hasVersion / dct:isVersionOf / dct:replaces / dct:isPartOf
    version: str | None = None              # version identifier string
    version_notes: str | None = None        # changelog / what changed
    derived_from: list[str] = []            # parent dataset source_ids or URIs
    supersedes: list[str] = []              # datasets this record replaces
    is_part_of: str | None = None           # URI of parent collection
    source_system: str | None = None        # originating system / database name
    processing_steps: list[str] = []        # pipeline / ETL steps applied
    source_metadata_url: str | None = None  # URL to original metadata record
    data_collection_start: str | None = None
    data_collection_end: str | None = None
    issued: str | None = None               # dct:issued – first publication date
    modified: str | None = None             # dct:modified – last modification date

    # ── Access & Endpoints (DCAT-AP 2.1, VoID, OGC) ──────────────────────────
    api_endpoint: str | None = None
    api_documentation_url: str | None = None
    sparql_endpoint: str | None = None      # VoID: void:sparqlEndpoint
    bulk_download_url: str | None = None
    wfs_endpoint: str | None = None         # OGC WFS (geographic features)
    wcs_endpoint: str | None = None         # OGC WCS (raster coverage)
    odata_endpoint: str | None = None       # OData REST endpoint
    download_urls: list[str] = []           # dcat:downloadURL (all distributions)
    media_types: list[str] = []             # dcat:mediaType – IANA MIME types

    # ── Statistical Methodology (SDMX 3.0, DDI-CDI) ──────────────────────────
    statistical_unit: str | None = None     # unit of observation, e.g. "persons", "enterprises"
    statistical_unit_confidence: float | None = Field(None, ge=0.0, le=1.0)
    statistical_population: str | None = None   # target population description
    collection_mode: str | None = None      # "survey", "administrative", "sensor", "transaction"
    imputation_method: str | None = None    # missing-value imputation approach
    seasonal_adjustment: str | None = None  # "SA", "NSA", "WDA", "none"
    classification_systems: list[str] = []  # e.g. ["NACE Rev.2", "ISIC 4", "NUTS3", "CPA"]
    classification_systems_confidence: float | None = Field(None, ge=0.0, le=1.0)
    reference_period: str | None = None     # canonical reference period, e.g. "2020Q1"
    reference_period_confidence: float | None = Field(None, ge=0.0, le=1.0)
    revision_policy: str | None = None      # revision / correction policy description
    coverage_rate: str | None = None        # e.g. "95 % of enterprises with ≥10 employees"
    sample_size: str | None = None          # sample size description or integer as string
    confidentiality_policy: str | None = None  # cell suppression / micro-aggregation rules
    embargo_date: str | None = None         # ISO 8601 date when embargo lifts

    # ── Data Quality (ISO 19115, DCAT-AP 2.1, DataCite) ──────────────────────
    accuracy_notes: str | None = None       # thematic / spatial / temporal accuracy
    completeness_notes: str | None = None
    consistency_notes: str | None = None    # logical consistency description
    validation_report_url: str | None = None
    known_issues: str | None = None
    quality_assurance_procedure: str | None = None  # ISO 19115: DQ_Element description

    # ── Geographic Metadata (ISO 19115, DCAT-AP 2.1) ─────────────────────────
    spatial_resolution: str | None = None   # e.g. "1 km", "NUTS3", "LAU2"
    coordinate_system: str | None = None    # CRS – e.g. "EPSG:4326", "ETRS89-LAEA"
    bounding_box: str | None = None         # WGS84: "minLon,minLat,maxLon,maxLat"
    geographic_level: str | None = None     # admin-level / NUTS-level description

    # ── Interoperability (SDMX, Eurostat, Wikidata, VoID) ────────────────────
    concept_uris: list[str] = []            # URIs to concept / variable definitions
    related_standards: list[str] = []       # related metadata or data standards
    wikidata_id: str | None = None          # Wikidata entity QID, e.g. "Q12345"
    eurostat_code: str | None = None        # Eurostat dataset code, e.g. "nama_10_gdp"
    sdmx_dataflow_id: str | None = None     # SDMX dataflow URN
    sdmx_agency_id: str | None = None       # SDMX agency identifier
    dsd_url: str | None = None              # SDMX Data Structure Definition URL
    linked_data_uri: str | None = None      # canonical dereferenceable linked-data URI

    # ── FAIR Principles ───────────────────────────────────────────────────────
    persistent_identifier: str | None = None   # DOI, Handle, ARK, PURL, etc.  (F)
    metadata_standard_uri: str | None = None   # URI of the metadata standard used (I)
    vocabulary_uris: list[str] = []            # controlled vocabularies / ontologies (I)
    reuse_conditions: str | None = None        # narrative reuse conditions (R)
    rights_statement: str | None = None        # dct:rights URI (R)

    # ── Citation (DataCite 4.4) ────────────────────────────────────────────────
    doi: str | None = None
    isbn: str | None = None
    citation_text: str | None = None            # ready-to-use formatted citation string
    preferred_citation_format: str | None = None  # "APA", "BibTeX", "Chicago", etc.
    publication_year: int | None = None
    creators: list[str] = []                    # DataCite: names / ORCIDs
    contributors: list[str] = []                # DataCite: role-qualified contributors
    funding_info: list[str] = []                # "funder: grant_number" strings
    related_identifiers: list[str] = []         # DataCite: DOI+relation-type pairs

    # ── Dublin Core extensions (terms beyond dct:* covered above) ────────────
    dc_type: str | None = None                  # dct:type, e.g. DCMI Types
    dc_subject: list[str] = []                  # dct:subject (free or controlled)
    dc_relation: list[str] = []                 # dct:relation
    dc_rights: str | None = None                # dct:rights (human-readable)
    dc_format: str | None = None                # dct:format (MIME or extent)
    dc_audience: list[str] = []                 # dct:audience
    dc_accrual_periodicity: str | None = None   # dct:accrualPeriodicity (RDF URI)
    dc_conforms_to: list[str] = []              # dct:conformsTo – standard URIs

    # ── AI & ML Usability (Croissant ML, schema.org/Dataset) ─────────────────
    query_hints: list[str] = []                 # example natural-language questions
    query_hints_confidence: float | None = Field(None, ge=0.0, le=1.0)
    typical_use_cases: list[str] = []           # intended analytical use cases
    typical_use_cases_confidence: float | None = Field(None, ge=0.0, le=1.0)
    not_suitable_for: list[str] = []            # explicit anti-use-cases
    training_data_suitability: Literal[
        "suitable", "restricted", "not_suitable", "unknown"
    ] | None = None
    ml_task_types: list[str] = []               # e.g. ["regression", "time_series_forecasting"]
    croissant_url: str | None = None            # URL to Croissant JSON-LD descriptor

    # ── LLM-extracted (original set) ──────────────────────────────────────────
    time_series_length: str | None = None
    time_series_length_confidence: float | None = Field(None, ge=0.0, le=1.0)
    methodology_url: str | None = None
    methodology_url_confidence: float | None = Field(None, ge=0.0, le=1.0)
    related_datasets: list[str] = []
    related_datasets_confidence: float | None = Field(None, ge=0.0, le=1.0)
    subject_classification: list[str] = []
    subject_classification_confidence: float | None = Field(None, ge=0.0, le=1.0)
    unit_of_measure: str | None = None
    unit_of_measure_confidence: float | None = Field(None, ge=0.0, le=1.0)
    observation_count_estimate: int | None = None
    observation_count_estimate_confidence: float | None = Field(None, ge=0.0, le=1.0)

    # ── Trust & quality signals ────────────────────────────────────────────────
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    completeness_score: float = Field(..., ge=0.0, le=1.0)
    freshness_score: float = Field(..., ge=0.0, le=1.0)
    link_healthy: bool | None = None

    # ── System ────────────────────────────────────────────────────────────────
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
