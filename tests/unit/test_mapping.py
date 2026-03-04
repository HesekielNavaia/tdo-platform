"""
Unit tests for schema detection, mapping tables, and helper functions.
"""
from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from src.pipeline.schema_detector import detect_schema
from src.pipeline.mapping_tables import (
    _frequency_map,
    _iso_date,
    SCHEMA_TO_MAPPING,
    SCHEMA_DETECTION_SIGNALS,
)


class TestSchemaDetector:
    def test_sdmx_detected(self):
        payload = {
            "data": {
                "dataflows": [
                    {
                        "id": "EMPLOYMENT",
                        "agencyID": "ESTAT",
                        "name": {"en": "Employment statistics"},
                    }
                ]
            },
            "meta": {"prepared": "2024-01-01"},
        }
        assert detect_schema(payload) == "SDMX"

    def test_dcat_detected(self):
        payload = {
            "@type": "dcat:Dataset",
            "dct:title": "My Dataset",
            "dcat:keyword": ["statistics", "employment"],
            "dcat:distribution": [],
        }
        assert detect_schema(payload) == "DCAT"

    def test_dublin_core_detected(self):
        payload = {
            "dc:title": "Population Data",
            "dc:identifier": "pop-001",
            "dc:publisher": "National Statistics Office",
        }
        assert detect_schema(payload) == "DublinCore"

    def test_ddi_detected(self):
        payload = {
            "stdyDscr": {
                "citation": {
                    "titlStmt": {"titl": "Labour Force Survey"},
                }
            }
        }
        assert detect_schema(payload) == "DDI"

    def test_world_bank_detected(self):
        payload = {
            "id": "1",
            "name": "World Development Indicators",
            "lastupdated": "2024-01-15",
            "sourceNote": "Various sources",
        }
        assert detect_schema(payload) == "WorldBank"

    def test_unknown_payload_returns_unknown(self):
        payload = {
            "completely_arbitrary_key": "some_value",
            "another_key": 42,
        }
        assert detect_schema(payload) == "unknown"

    def test_empty_payload_returns_unknown(self):
        assert detect_schema({}) == "unknown"


class TestFrequencyMap:
    def test_sdmx_annual_code(self):
        assert _frequency_map("A") == "annual"

    def test_sdmx_monthly_code(self):
        assert _frequency_map("M") == "monthly"

    def test_sdmx_weekly_code(self):
        assert _frequency_map("W") == "weekly"

    def test_sdmx_daily_code(self):
        assert _frequency_map("D") == "daily"

    def test_sdmx_quarterly_code(self):
        # quarterly maps to annual tier
        assert _frequency_map("Q") == "annual"

    def test_plain_text_annual(self):
        assert _frequency_map("annual") == "annual"

    def test_plain_text_monthly(self):
        assert _frequency_map("monthly") == "monthly"

    def test_plain_text_weekly(self):
        assert _frequency_map("weekly") == "weekly"

    def test_plain_text_daily(self):
        assert _frequency_map("daily") == "daily"

    def test_plain_text_irregular(self):
        assert _frequency_map("irregular") == "irregular"

    def test_none_returns_none(self):
        assert _frequency_map(None) is None

    def test_all_valid_values_are_mvm_valid(self):
        valid_output = {"daily", "weekly", "monthly", "annual", "irregular"}
        codes = ["A", "S", "Q", "M", "W", "D", "H", "N", "B",
                 "annual", "yearly", "quarterly", "monthly", "weekly",
                 "daily", "irregular", "unknown", "other"]
        for code in codes:
            result = _frequency_map(code)
            assert result in valid_output, f"Code {code!r} mapped to invalid value {result!r}"

    @given(st.text())
    def test_frequency_map_never_raises(self, s: str):
        """_frequency_map should never raise on any string input."""
        result = _frequency_map(s)
        valid = {"daily", "weekly", "monthly", "annual", "irregular", None}
        assert result in valid


class TestIsoDate:
    def test_iso_date_already_correct(self):
        assert _iso_date("2024-01-15") == "2024-01-15"

    def test_year_only(self):
        assert _iso_date("2024") == "2024"

    def test_yyyymm_format(self):
        assert _iso_date("202401") == "2024-01"

    def test_dd_mm_yyyy_returns_year(self):
        result = _iso_date("15/01/2024")
        assert result == "2024"

    def test_none_returns_none(self):
        assert _iso_date(None) is None

    def test_empty_string_returns_none(self):
        assert _iso_date("") is None

    @given(st.text())
    def test_iso_date_returns_string_or_none_never_raises(self, s: str):
        """_iso_date should return str or None and never raise."""
        result = _iso_date(s)
        assert result is None or isinstance(result, str)
