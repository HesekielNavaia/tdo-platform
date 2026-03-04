"""
Unit tests for the FastAPI application.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

# Use a test API key
API_KEY = "dev-key-123"
AUTH_HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/v1/health")
        assert resp.status_code == 200

    def test_health_contains_status(self, client):
        resp = client.get("/v1/health")
        data = resp.json()
        assert "status" in data
        assert data["status"] == "ok"

    def test_health_requires_no_auth(self, client):
        # /v1/health is a public endpoint
        resp = client.get("/v1/health")
        assert resp.status_code == 200


class TestAuthentication:
    def test_datasets_rejects_missing_api_key(self, client):
        resp = client.get("/v1/datasets")
        assert resp.status_code == 401

    def test_datasets_rejects_wrong_api_key(self, client):
        resp = client.get("/v1/datasets", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401

    def test_datasets_accepts_valid_api_key(self, client):
        resp = client.get("/v1/datasets", headers=AUTH_HEADERS)
        assert resp.status_code == 200

    def test_portals_requires_auth(self, client):
        resp = client.get("/v1/portals")
        assert resp.status_code == 401

    def test_portals_accepts_valid_key(self, client):
        resp = client.get("/v1/portals", headers=AUTH_HEADERS)
        assert resp.status_code == 200


class TestDatasetsEndpoint:
    def test_datasets_returns_list(self, client):
        resp = client.get("/v1/datasets", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_datasets_validates_min_confidence(self, client):
        resp = client.get(
            "/v1/datasets",
            headers=AUTH_HEADERS,
            params={"min_confidence": 1.5},  # Invalid: > 1.0
        )
        assert resp.status_code == 422

    def test_datasets_validates_limit_max(self, client):
        resp = client.get(
            "/v1/datasets",
            headers=AUTH_HEADERS,
            params={"limit": 200},  # Invalid: > 100
        )
        assert resp.status_code == 422

    def test_datasets_accepts_query_params(self, client):
        resp = client.get(
            "/v1/datasets",
            headers=AUTH_HEADERS,
            params={"q": "unemployment finland", "limit": 10},
        )
        assert resp.status_code == 200

    def test_datasets_accepts_geo_filter(self, client):
        resp = client.get(
            "/v1/datasets",
            headers=AUTH_HEADERS,
            params={"geo": "FI,SE"},
        )
        assert resp.status_code == 200


class TestPortalsEndpoint:
    def test_portals_returns_list(self, client):
        resp = client.get("/v1/portals", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_portals_contains_all_five(self, client):
        resp = client.get("/v1/portals", headers=AUTH_HEADERS)
        data = resp.json()
        portal_ids = {p["portal_id"] for p in data}
        assert "statistics_finland" in portal_ids
        assert "world_bank" in portal_ids
        assert "eurostat" in portal_ids
        assert "oecd" in portal_ids
        assert "un_data" in portal_ids


class TestStatsEndpoint:
    def test_stats_returns_200(self, client):
        resp = client.get("/v1/stats")
        assert resp.status_code == 200

    def test_stats_is_public(self, client):
        # /v1/stats is public endpoint
        resp = client.get("/v1/stats")
        assert resp.status_code == 200

    def test_stats_contains_counts(self, client):
        resp = client.get("/v1/stats")
        data = resp.json()
        assert "total_datasets" in data
        assert "by_portal" in data


class TestQueryEndpoint:
    def test_post_query_returns_200(self, client):
        resp = client.post(
            "/v1/query",
            headers=AUTH_HEADERS,
            json={"question": "unemployment statistics Finland"},
        )
        assert resp.status_code == 200

    def test_post_query_returns_structured(self, client):
        resp = client.post(
            "/v1/query",
            headers=AUTH_HEADERS,
            json={"question": "labour market data"},
        )
        data = resp.json()
        assert "question" in data
        assert "results" in data


class TestDatasetByIdEndpoint:
    def test_dataset_by_id_returns_404(self, client):
        resp = client.get("/v1/datasets/nonexistent-id", headers=AUTH_HEADERS)
        assert resp.status_code == 404

    def test_similar_returns_empty(self, client):
        resp = client.get("/v1/datasets/some-id/similar", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
