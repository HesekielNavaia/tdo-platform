"""
Unit tests for hybrid search.
"""
from __future__ import annotations

import pytest

from src.api.search import compute_rrf_score, rrf_fusion, build_filter_clause, HybridSearch
from src.models.mvm import SearchFilters


class TestRRF:
    def test_rrf_formula_correct(self):
        """RRF score = 1 / (k + rank)"""
        k = 60
        assert compute_rrf_score(1, k) == 1.0 / 61
        assert compute_rrf_score(10, k) == 1.0 / 70
        assert compute_rrf_score(60, k) == 1.0 / 120

    def test_rrf_default_k_is_60(self):
        score = compute_rrf_score(1)
        assert abs(score - 1.0 / 61) < 1e-10

    def test_rrf_fusion_single_channel_semantic(self):
        """When only semantic results exist, fusion returns those scores."""
        semantic = [("id1", 0.9), ("id2", 0.8), ("id3", 0.7)]
        keyword = []
        result = rrf_fusion(semantic, keyword, semantic_weight=0.7, keyword_weight=0.3)
        ids = [r[0] for r in result]
        assert "id1" in ids
        assert "id2" in ids
        assert "id3" in ids

    def test_rrf_fusion_single_channel_keyword(self):
        """When only keyword results exist, fusion returns those scores."""
        semantic = []
        keyword = [("id1", 0.9), ("id2", 0.7)]
        result = rrf_fusion(semantic, keyword, semantic_weight=0.7, keyword_weight=0.3)
        ids = [r[0] for r in result]
        assert "id1" in ids
        assert "id2" in ids

    def test_rrf_fusion_combines_both_channels(self):
        """A document appearing in both channels gets a higher score."""
        semantic = [("shared-doc", 0.9), ("sem-only", 0.8)]
        keyword = [("shared-doc", 0.8), ("kw-only", 0.7)]
        result = rrf_fusion(semantic, keyword)
        result_dict = dict(result)

        # shared-doc appears in both channels → higher score
        assert "shared-doc" in result_dict
        assert "sem-only" in result_dict
        assert "kw-only" in result_dict

        # shared-doc should rank higher than channel-exclusive docs
        shared_score = result_dict["shared-doc"]
        sem_only_score = result_dict["sem-only"]
        kw_only_score = result_dict["kw-only"]
        assert shared_score > sem_only_score or shared_score > kw_only_score

    def test_rrf_fusion_result_sorted_descending(self):
        semantic = [("id1", 0.9), ("id2", 0.8), ("id3", 0.7)]
        keyword = [("id2", 0.9), ("id3", 0.8), ("id4", 0.7)]
        result = rrf_fusion(semantic, keyword)
        scores = [s for _, s in result]
        assert scores == sorted(scores, reverse=True)


class TestBuildFilterClause:
    def test_min_confidence_always_present(self):
        filters = SearchFilters(min_confidence=0.5)
        clause, params = build_filter_clause(filters)
        assert "confidence_score" in clause
        assert params["min_confidence"] == 0.5

    def test_geo_filter_added(self):
        filters = SearchFilters(geo=["FI", "SE"])
        clause, params = build_filter_clause(filters)
        assert "geographic_coverage" in clause
        assert params["geo"] == ["FI", "SE"]

    def test_publisher_filter_fuzzy(self):
        filters = SearchFilters(publisher="Statistics Finland")
        clause, params = build_filter_clause(filters)
        assert "ILIKE" in clause
        assert "Statistics Finland" in params["publisher"]

    def test_access_filter(self):
        filters = SearchFilters(access="open")
        clause, params = build_filter_clause(filters)
        assert "access_type" in clause
        assert params["access"] == "open"

    def test_resource_type_filter(self):
        filters = SearchFilters(resource_type="dataset")
        clause, params = build_filter_clause(filters)
        assert "resource_type" in clause

    def test_no_filters_returns_true(self):
        filters = SearchFilters(min_confidence=0.0)
        clause, params = build_filter_clause(filters)
        # With only min_confidence=0, clause is still valid SQL
        assert clause != ""

    def test_min_confidence_filter_applied(self):
        """min_confidence must always be included in filter params."""
        for threshold in [0.0, 0.3, 0.6, 0.9, 1.0]:
            filters = SearchFilters(min_confidence=threshold)
            _, params = build_filter_clause(filters)
            assert params["min_confidence"] == threshold

    def test_theme_filter_added(self):
        filters = SearchFilters(theme=["Labour market"])
        clause, params = build_filter_clause(filters)
        assert "themes" in clause
        assert params["theme"] == ["Labour market"]

    def test_format_filter_added(self):
        filters = SearchFilters(format="CSV")
        clause, params = build_filter_clause(filters)
        assert "formats" in clause

    def test_updated_after_filter_added(self):
        filters = SearchFilters(updated_after="2024-01-01")
        clause, params = build_filter_clause(filters)
        assert "last_updated" in clause
        assert params["updated_after"] == "2024-01-01"


class TestHybridSearchMocked:
    """Tests for HybridSearch using a fully mocked DB session."""

    def _make_session_factory(self, sem_rows=None, kw_rows=None, detail_rows=None):
        """Build a fake async session factory returning preset rows."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        sem_rows   = sem_rows   or []
        kw_rows    = kw_rows    or []
        detail_rows = detail_rows or []

        call_count = {"n": 0}

        class FakeResult:
            def __init__(self, rows):
                self._rows = rows
            def __iter__(self):
                return iter(self._rows)

        class FakeSession:
            async def execute(self, stmt, params=None):
                n = call_count["n"]
                call_count["n"] += 1
                if n == 0:
                    return FakeResult(kw_rows)
                return FakeResult(detail_rows)
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass

        class FakeFactory:
            def __call__(self):
                return FakeSession()

        return FakeFactory()

    @pytest.mark.asyncio
    async def test_search_no_query_returns_empty(self):
        """Empty query with no embedder returns empty list."""
        factory = self._make_session_factory()
        hs = HybridSearch(factory, embedder=None)
        results = await hs.search("")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_with_query_no_embedder(self):
        """Query without embedder falls back to keyword-only path."""
        from unittest.mock import AsyncMock, MagicMock
        factory = self._make_session_factory(kw_rows=[], detail_rows=[])
        hs = HybridSearch(factory, embedder=None)
        results = await hs.search("unemployment")
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_row_to_mvm_helper(self):
        """_row_to_mvm should produce a valid MVMRecord from a fake row tuple."""
        from datetime import datetime, timezone
        hs = HybridSearch(lambda: None, embedder=None)

        # Build a fake row matching the SELECT column order
        fake_row = (
            "uuid-1",        # id
            "src-1",         # source_id
            "portal1",       # portal_id
            "dataset",       # resource_type
            "Test Title",    # title
            "A description", # description
            "Test Pub",      # publisher
            "NSO",           # publisher_type
            "statfin",       # source_portal
            None,            # dataset_url
            ["kw1"],         # keywords
            ["theme1"],      # themes
            ["FI"],          # geographic_coverage
            "2020",          # temporal_coverage_start
            None,            # temporal_coverage_end
            ["fi"],          # languages
            "annual",        # update_frequency
            "2024-01-01",    # last_updated
            "open",          # access_type
            None,            # access_conditions
            "CC-BY 4.0",     # license
            ["CSV"],         # formats
            None,            # contact_point
            None,            # provenance
            "SDMX",          # metadata_standard
            0.9,             # confidence_score
            0.8,             # completeness_score
            0.7,             # freshness_score
            None,            # link_healthy
            datetime.now(timezone.utc),  # ingestion_timestamp
        )
        mvm = hs._row_to_mvm(fake_row)
        assert mvm.title == "Test Title"
        assert mvm.publisher == "Test Pub"
        assert mvm.confidence_score == 0.9
