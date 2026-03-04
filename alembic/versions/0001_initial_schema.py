"""Initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-03-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.create_table(
        "pipeline_runs",
        sa.Column("run_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("portal_id", sa.Text, nullable=False),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("source_id", sa.Text),
        sa.Column("error_message", sa.Text),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("retry_count", sa.Integer, default=0),
    )
    op.create_index("idx_pipeline_resume", "pipeline_runs", ["portal_id", "stage", "status"])

    op.create_table(
        "dataset_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_id", UUID(as_uuid=True)),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("mvm_snapshot", JSONB, nullable=False),
        sa.Column("pipeline_run_id", UUID(as_uuid=True)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "datasets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", sa.Text, nullable=False),
        sa.Column("portal_id", sa.Text, nullable=False),
        sa.Column("current_version_id", UUID(as_uuid=True)),
        sa.Column("resource_type", sa.Text, nullable=False, server_default="dataset"),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("publisher", sa.Text, nullable=False),
        sa.Column("publisher_type", sa.Text, nullable=False),
        sa.Column("source_portal", sa.Text),
        sa.Column("dataset_url", sa.Text),
        sa.Column("keywords", sa.ARRAY(sa.Text)),
        sa.Column("themes", sa.ARRAY(sa.Text)),
        sa.Column("geographic_coverage", sa.ARRAY(sa.Text)),
        sa.Column("temporal_coverage_start", sa.Text),
        sa.Column("temporal_coverage_end", sa.Text),
        sa.Column("languages", sa.ARRAY(sa.Text)),
        sa.Column("update_frequency", sa.Text),
        sa.Column("last_updated", sa.Text),
        sa.Column("access_type", sa.Text, nullable=False),
        sa.Column("access_conditions", sa.Text),
        sa.Column("license", sa.Text),
        sa.Column("formats", sa.ARRAY(sa.Text)),
        sa.Column("contact_point", sa.Text),
        sa.Column("provenance", sa.Text),
        sa.Column("metadata_standard", sa.Text),
        sa.Column("confidence_score", sa.Float),
        sa.Column("completeness_score", sa.Float),
        sa.Column("freshness_score", sa.Float),
        sa.Column("link_healthy", sa.Boolean),
        sa.Column("ingestion_timestamp", sa.TIMESTAMP(timezone=True)),
        sa.Column("embedding", JSONB),
        sa.UniqueConstraint("source_id", "portal_id", name="uq_dataset_source_portal"),
    )
    op.create_foreign_key(
        "fk_datasets_version", "datasets", "dataset_versions",
        ["current_version_id"], ["id"]
    )

    op.create_table(
        "dataset_aliases",
        sa.Column("alias_source_id", sa.Text, primary_key=True),
        sa.Column("portal_id", sa.Text, primary_key=True),
        sa.Column("canonical_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id")),
        sa.Column("first_seen", sa.TIMESTAMP(timezone=True)),
    )

    op.create_table(
        "metadata_review_queue",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id")),
        sa.Column("pipeline_run_id", UUID(as_uuid=True)),
        sa.Column("confidence_score", sa.Float),
        sa.Column("field_confidence", JSONB),
        sa.Column("field_evidence", JSONB),
        sa.Column("review_reason", sa.Text),
        sa.Column("reviewed", sa.Boolean, default=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "processing_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("mvm_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id")),
        sa.Column("raw_blob_path", sa.Text),
        sa.Column("raw_payload_hash", sa.Text),
        sa.Column("parser_version", sa.Text),
        sa.Column("harmoniser_version", sa.Text),
        sa.Column("embedding_model_version", sa.Text),
        sa.Column("pipeline_run_id", UUID(as_uuid=True)),
        sa.Column("field_confidence", JSONB),
        sa.Column("field_evidence", JSONB),
        sa.Column("llm_model_used", sa.Text),
        sa.Column("llm_fallback_triggered", sa.Boolean),
        sa.Column("flagged_for_review", sa.Boolean),
        sa.Column("review_reason", sa.Text),
    )

    # FK from dataset_versions to datasets (after datasets table created)
    op.create_foreign_key(
        "fk_dataset_versions_dataset", "dataset_versions", "datasets",
        ["dataset_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_table("processing_records")
    op.drop_table("metadata_review_queue")
    op.drop_table("dataset_aliases")
    op.drop_table("datasets")
    op.drop_table("dataset_versions")
    op.drop_table("pipeline_runs")
