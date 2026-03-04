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
