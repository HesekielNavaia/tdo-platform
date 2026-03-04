"""
Unit tests for MVM Pydantic models.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.models.mvm import MVMRecord, SearchFilters, SearchResult, PortalHealth


VALID_MINIMAL_RECORD = {
    "id": "test-uuid-1",
    "source_id": "src-001",
    "title": "Test Dataset",
    "publisher": "Test Publisher",
    "publisher_type": "NSO",
    "source_portal": "https://example.com",
    "access_type": "open",
    "metadata_standard": "SDMX",
    "confidence_score": 0.8,
    "completeness_score": 0.7,
    "freshness_score": 0.9,
    "ingestion_timestamp": datetime.now(timezone.utc),
}


class TestMVMRecord:
    def test_accepts_valid_minimal_record(self):
        record = MVMRecord(**VALID_MINIMAL_RECORD)
        assert record.title == "Test Dataset"
        assert record.publisher == "Test Publisher"

    def test_rejects_missing_title(self):
        data = {**VALID_MINIMAL_RECORD}
        del data["title"]
        with pytest.raises(ValidationError):
            MVMRecord(**data)

    def test_rejects_missing_publisher(self):
        data = {**VALID_MINIMAL_RECORD}
        del data["publisher"]
        with pytest.raises(ValidationError):
            MVMRecord(**data)

    def test_rejects_missing_access_type(self):
        data = {**VALID_MINIMAL_RECORD}
        del data["access_type"]
        with pytest.raises(ValidationError):
            MVMRecord(**data)

    def test_rejects_missing_metadata_standard(self):
        data = {**VALID_MINIMAL_RECORD}
        del data["metadata_standard"]
        with pytest.raises(ValidationError):
            MVMRecord(**data)

    def test_rejects_invalid_publisher_type(self):
        data = {**VALID_MINIMAL_RECORD, "publisher_type": "INVALID"}
        with pytest.raises(ValidationError):
            MVMRecord(**data)

    def test_rejects_invalid_resource_type(self):
        data = {**VALID_MINIMAL_RECORD, "resource_type": "INVALID"}
        with pytest.raises(ValidationError):
            MVMRecord(**data)

    def test_rejects_invalid_access_type(self):
        data = {**VALID_MINIMAL_RECORD, "access_type": "INVALID"}
        with pytest.raises(ValidationError):
            MVMRecord(**data)

    def test_rejects_invalid_metadata_standard(self):
        data = {**VALID_MINIMAL_RECORD, "metadata_standard": "INVALID"}
        with pytest.raises(ValidationError):
            MVMRecord(**data)

    def test_rejects_invalid_update_frequency(self):
        data = {**VALID_MINIMAL_RECORD, "update_frequency": "INVALID"}
        with pytest.raises(ValidationError):
            MVMRecord(**data)

    def test_confidence_score_rejects_below_zero(self):
        data = {**VALID_MINIMAL_RECORD, "confidence_score": -0.1}
        with pytest.raises(ValidationError):
            MVMRecord(**data)

    def test_confidence_score_rejects_above_one(self):
        data = {**VALID_MINIMAL_RECORD, "confidence_score": 1.1}
        with pytest.raises(ValidationError):
            MVMRecord(**data)

    def test_completeness_score_rejects_below_zero(self):
        data = {**VALID_MINIMAL_RECORD, "completeness_score": -0.1}
        with pytest.raises(ValidationError):
            MVMRecord(**data)

    def test_completeness_score_rejects_above_one(self):
        data = {**VALID_MINIMAL_RECORD, "completeness_score": 1.1}
        with pytest.raises(ValidationError):
            MVMRecord(**data)

    def test_freshness_score_rejects_below_zero(self):
        data = {**VALID_MINIMAL_RECORD, "freshness_score": -0.5}
        with pytest.raises(ValidationError):
            MVMRecord(**data)

    def test_freshness_score_rejects_above_one(self):
        data = {**VALID_MINIMAL_RECORD, "freshness_score": 1.5}
        with pytest.raises(ValidationError):
            MVMRecord(**data)

    def test_confidence_score_boundary_zero(self):
        data = {**VALID_MINIMAL_RECORD, "confidence_score": 0.0}
        record = MVMRecord(**data)
        assert record.confidence_score == 0.0

    def test_confidence_score_boundary_one(self):
        data = {**VALID_MINIMAL_RECORD, "confidence_score": 1.0}
        record = MVMRecord(**data)
        assert record.confidence_score == 1.0

    def test_optional_fields_default_to_none_or_empty(self):
        record = MVMRecord(**VALID_MINIMAL_RECORD)
        assert record.description is None
        assert record.dataset_url is None
        assert record.keywords == []
        assert record.themes == []
        assert record.geographic_coverage == []
        assert record.languages == []
        assert record.license is None

    def test_all_valid_publisher_types(self):
        for pt in ["NSO", "IO", "NGO", "other"]:
            data = {**VALID_MINIMAL_RECORD, "publisher_type": pt}
            record = MVMRecord(**data)
            assert record.publisher_type == pt

    def test_all_valid_resource_types(self):
        for rt in ["dataset", "table", "indicator", "collection", "unknown"]:
            data = {**VALID_MINIMAL_RECORD, "resource_type": rt}
            record = MVMRecord(**data)
            assert record.resource_type == rt

    def test_all_valid_access_types(self):
        for at in ["open", "restricted", "embargoed"]:
            data = {**VALID_MINIMAL_RECORD, "access_type": at}
            record = MVMRecord(**data)
            assert record.access_type == at

    def test_all_valid_metadata_standards(self):
        for ms in ["SDMX", "DCAT", "DublinCore", "DDI", "other", "unknown"]:
            data = {**VALID_MINIMAL_RECORD, "metadata_standard": ms}
            record = MVMRecord(**data)
            assert record.metadata_standard == ms

    def test_all_valid_update_frequencies(self):
        for freq in ["daily", "weekly", "monthly", "annual", "irregular"]:
            data = {**VALID_MINIMAL_RECORD, "update_frequency": freq}
            record = MVMRecord(**data)
            assert record.update_frequency == freq
