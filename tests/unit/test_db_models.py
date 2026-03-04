"""
Unit tests for SQLAlchemy database models.
"""
from __future__ import annotations

import pytest


class TestDbModelsImport:
    def test_can_import_all_models(self):
        from src.models.db import (
            Dataset,
            DatasetVersion,
            DatasetAlias,
            MetadataReviewQueue,
            ProcessingRecord,
            PipelineRun,
            Base,
        )
        assert Dataset is not None
        assert DatasetVersion is not None
        assert DatasetAlias is not None
        assert MetadataReviewQueue is not None
        assert ProcessingRecord is not None
        assert PipelineRun is not None

    def test_dataset_has_correct_columns(self):
        from src.models.db import Dataset
        cols = {c.key for c in Dataset.__table__.columns}
        required_cols = {
            "id", "source_id", "portal_id", "title", "description",
            "publisher", "publisher_type", "resource_type", "source_portal",
            "dataset_url", "keywords", "themes", "geographic_coverage",
            "temporal_coverage_start", "temporal_coverage_end", "languages",
            "update_frequency", "last_updated", "access_type", "access_conditions",
            "license", "formats", "contact_point", "provenance", "metadata_standard",
            "confidence_score", "completeness_score", "freshness_score",
            "link_healthy", "ingestion_timestamp", "embedding",
        }
        assert required_cols.issubset(cols)

    def test_dataset_version_has_correct_columns(self):
        from src.models.db import DatasetVersion
        cols = {c.key for c in DatasetVersion.__table__.columns}
        assert {"id", "dataset_id", "version_number", "mvm_snapshot", "pipeline_run_id", "created_at"}.issubset(cols)

    def test_dataset_alias_has_correct_columns(self):
        from src.models.db import DatasetAlias
        cols = {c.key for c in DatasetAlias.__table__.columns}
        assert {"alias_source_id", "portal_id", "canonical_id", "first_seen"}.issubset(cols)

    def test_metadata_review_queue_has_correct_columns(self):
        from src.models.db import MetadataReviewQueue
        cols = {c.key for c in MetadataReviewQueue.__table__.columns}
        assert {
            "id", "dataset_id", "pipeline_run_id", "confidence_score",
            "field_confidence", "field_evidence", "review_reason", "reviewed", "created_at"
        }.issubset(cols)

    def test_processing_record_has_correct_columns(self):
        from src.models.db import ProcessingRecord
        cols = {c.key for c in ProcessingRecord.__table__.columns}
        assert {
            "id", "mvm_id", "raw_blob_path", "raw_payload_hash",
            "parser_version", "harmoniser_version", "embedding_model_version",
            "pipeline_run_id", "field_confidence", "field_evidence",
            "llm_model_used", "llm_fallback_triggered",
            "flagged_for_review", "review_reason"
        }.issubset(cols)

    def test_pipeline_run_has_correct_columns(self):
        from src.models.db import PipelineRun
        cols = {c.key for c in PipelineRun.__table__.columns}
        assert {
            "run_id", "portal_id", "stage", "status", "source_id",
            "error_message", "started_at", "completed_at", "retry_count"
        }.issubset(cols)

    def test_dataset_has_unique_constraint(self):
        from src.models.db import Dataset
        unique_constraints = {c.name for c in Dataset.__table__.constraints if hasattr(c, 'name') and c.name}
        assert "uq_dataset_source_portal" in unique_constraints
