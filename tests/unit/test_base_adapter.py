"""
Unit tests for the base portal adapter.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator

import pytest

from src.adapters.base import BasePortalAdapter, RawRecord, AdapterHealth


class ConcreteAdapter(BasePortalAdapter):
    portal_id = "test_portal"
    base_url = "https://example.com"
    rate_limit_rps = 2.0  # 2 requests/sec for fast tests
    adapter_type = "api"

    async def fetch_catalogue(self) -> AsyncIterator[RawRecord]:
        yield self._make_record("src-001", {"id": "src-001", "title": "Test"})

    async def fetch_record(self, source_id: str) -> RawRecord:
        return self._make_record(source_id, {"id": source_id, "title": "Test"})

    def get_portal_defaults(self) -> dict[str, Any]:
        return {"_publisher": "Test Publisher", "_publisher_type": "NSO"}


class TestBaseAdapter:
    def test_adapter_instantiation(self):
        adapter = ConcreteAdapter()
        assert adapter.portal_id == "test_portal"
        assert adapter.adapter_type == "api"

    def test_hash_payload_is_sha256(self):
        adapter = ConcreteAdapter()
        payload = {"id": "123", "title": "Test"}
        h = adapter._hash_payload(payload)
        assert len(h) == 64  # SHA-256 hex length
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_payload_deterministic(self):
        adapter = ConcreteAdapter()
        payload = {"id": "123", "title": "Test"}
        h1 = adapter._hash_payload(payload)
        h2 = adapter._hash_payload(payload)
        assert h1 == h2

    def test_make_record_sets_hash(self):
        adapter = ConcreteAdapter()
        payload = {"id": "abc", "value": 42}
        record = adapter._make_record("abc", payload)
        assert record.raw_payload_hash is not None
        assert len(record.raw_payload_hash) == 64

    def test_make_record_sets_source_id(self):
        adapter = ConcreteAdapter()
        record = adapter._make_record("my-src-id", {"id": "x"})
        assert record.source_id == "my-src-id"

    def test_make_record_sets_portal_id(self):
        adapter = ConcreteAdapter()
        record = adapter._make_record("x", {})
        assert record.portal_id == "test_portal"

    def test_check_robots_returns_true_for_api_adapter(self):
        adapter = ConcreteAdapter()
        result = asyncio.run(adapter.check_robots())
        assert result is True

    @pytest.mark.asyncio
    async def test_rate_limiter_enforces_delay(self):
        """Rate limiter must enforce minimum delay between requests."""
        adapter = ConcreteAdapter()
        adapter.rate_limit_rps = 2.0  # 0.5s min interval
        times = []

        import respx
        import httpx as httpx_lib

        # We test the rate limiting by calling _rate_limited_get twice
        # and measuring the elapsed time
        with respx.mock:
            respx.get("https://example.com/test").mock(
                return_value=httpx_lib.Response(200, json={"ok": True})
            )
            async with httpx_lib.AsyncClient() as client:
                t0 = time.monotonic()
                await adapter._rate_limited_get(client, "https://example.com/test")
                t1 = time.monotonic()
                await adapter._rate_limited_get(client, "https://example.com/test")
                t2 = time.monotonic()

        second_call_gap = t2 - t1
        # With 2 rps, min gap is 0.5s
        assert second_call_gap >= 0.4, f"Expected >= 0.4s gap, got {second_call_gap:.3f}s"
