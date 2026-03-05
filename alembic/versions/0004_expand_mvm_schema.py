"""Expand MVM schema – multi-standard metadata fields (v2)

Adds ~80 new optional columns to the datasets table covering:
  DCAT-AP 2.1 · W3C DCAT · SDMX 3.0 / SDMX-JSON 2.0 · DDI-CDI
  Dublin Core terms + refinements · ISO 19115 · DataCite 4.4
  schema.org/Dataset · FAIR principles · Croissant ML · VoID

Revision ID: 0004_expand_mvm_schema
Revises: 0003_add_llm_description_fields
Create Date: 2026-03-05
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_expand_mvm_schema"
down_revision = "0003_add_llm_description_fields"
branch_labels = None
depends_on = None

# (column_name, sa_type)
TEXT_COLUMNS = [
    # Extended Provenance
    "version",
    "version_notes",
    "is_part_of",
    "source_system",
    "source_metadata_url",
    "data_collection_start",
    "data_collection_end",
    "issued",
    "modified",
    "license_uri",
    "contact_email",
    # Access & Endpoints
    "api_endpoint",
    "api_documentation_url",
    "sparql_endpoint",
    "bulk_download_url",
    "wfs_endpoint",
    "wcs_endpoint",
    "odata_endpoint",
    # Statistical Methodology
    "statistical_unit",
    "statistical_population",
    "collection_mode",
    "imputation_method",
    "seasonal_adjustment",
    "reference_period",
    "revision_policy",
    "coverage_rate",
    "sample_size",
    "confidentiality_policy",
    "embargo_date",
    # Data Quality
    "accuracy_notes",
    "completeness_notes",
    "consistency_notes",
    "validation_report_url",
    "known_issues",
    "quality_assurance_procedure",
    # Geographic
    "spatial_resolution",
    "coordinate_system",
    "bounding_box",
    "geographic_level",
    # Interoperability
    "wikidata_id",
    "eurostat_code",
    "sdmx_dataflow_id",
    "sdmx_agency_id",
    "dsd_url",
    "linked_data_uri",
    # FAIR
    "persistent_identifier",
    "metadata_standard_uri",
    "reuse_conditions",
    "rights_statement",
    # Citation / DataCite 4.4
    "doi",
    "isbn",
    "citation_text",
    "preferred_citation_format",
    # Dublin Core extensions
    "dc_type",
    "dc_rights",
    "dc_format",
    "dc_accrual_periodicity",
    # AI & ML
    "training_data_suitability",
    "croissant_url",
]

ARRAY_COLUMNS = [
    # Extended Provenance
    "derived_from",
    "supersedes",
    "processing_steps",
    # Access & Endpoints
    "download_urls",
    "media_types",
    # Statistical Methodology
    "classification_systems",
    # Interoperability
    "concept_uris",
    "related_standards",
    "vocabulary_uris",
    # Citation / DataCite 4.4
    "creators",
    "contributors",
    "funding_info",
    "related_identifiers",
    # Dublin Core extensions
    "dc_subject",
    "dc_relation",
    "dc_audience",
    "dc_conforms_to",
    # AI & ML
    "query_hints",
    "typical_use_cases",
    "not_suitable_for",
    "ml_task_types",
]

FLOAT_COLUMNS = [
    "statistical_unit_confidence",
    "classification_systems_confidence",
    "reference_period_confidence",
    "query_hints_confidence",
    "typical_use_cases_confidence",
]

INTEGER_COLUMNS = [
    "publication_year",
]


def upgrade() -> None:
    for col in TEXT_COLUMNS:
        op.add_column("datasets", sa.Column(col, sa.Text(), nullable=True))
    for col in ARRAY_COLUMNS:
        op.add_column("datasets", sa.Column(col, sa.ARRAY(sa.Text()), nullable=True))
    for col in FLOAT_COLUMNS:
        op.add_column("datasets", sa.Column(col, sa.Float(), nullable=True))
    for col in INTEGER_COLUMNS:
        op.add_column("datasets", sa.Column(col, sa.Integer(), nullable=True))

    # Useful indexes for common filter / join patterns
    op.create_index("ix_datasets_doi", "datasets", ["doi"], unique=False)
    op.create_index("ix_datasets_wikidata_id", "datasets", ["wikidata_id"], unique=False)
    op.create_index("ix_datasets_eurostat_code", "datasets", ["eurostat_code"], unique=False)
    op.create_index("ix_datasets_sdmx_dataflow_id", "datasets", ["sdmx_dataflow_id"], unique=False)
    op.create_index("ix_datasets_persistent_identifier", "datasets", ["persistent_identifier"], unique=False)
    op.create_index("ix_datasets_embargo_date", "datasets", ["embargo_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_datasets_embargo_date", table_name="datasets")
    op.drop_index("ix_datasets_persistent_identifier", table_name="datasets")
    op.drop_index("ix_datasets_sdmx_dataflow_id", table_name="datasets")
    op.drop_index("ix_datasets_eurostat_code", table_name="datasets")
    op.drop_index("ix_datasets_wikidata_id", table_name="datasets")
    op.drop_index("ix_datasets_doi", table_name="datasets")

    all_cols = (
        list(reversed(TEXT_COLUMNS))
        + list(reversed(ARRAY_COLUMNS))
        + list(reversed(FLOAT_COLUMNS))
        + list(reversed(INTEGER_COLUMNS))
    )
    for col in all_cols:
        op.drop_column("datasets", col)
