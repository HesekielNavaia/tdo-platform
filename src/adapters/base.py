"""
Base portal adapter — abstract class for all TDO portal adapters.
Provides rate limiting, retry logic, robots.txt checking, and raw payload hashing.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Literal

import httpx
import structlog

log = structlog.get_logger(__name__)

ADAPTER_VERSION = "0.1.0"


@dataclass
class RawRecord:
    source_id: str
    portal_id: str
    raw_payload: dict[str, Any]
    raw_payload_hash: str
    adapter_type: Literal["api", "html", "document"]
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AdapterHealth:
    portal_id: str
    status: Literal["healthy", "degraded", "unhealthy", "unknown"]
    last_check: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    latency_ms: float | None = None
    error_message: str | None = None
    records_available: int | None = None


class BasePortalAdapter(ABC):
    portal_id: str
    base_url: str
    rate_limit_rps: float = 1.0
    adapter_type: Literal["api", "html", "document"] = "api"

    def __init__(self, rate_limit_rps: float | None = None):
        if rate_limit_rps is not None:
            self.rate_limit_rps = rate_limit_rps
        self._last_request_time: float = 0.0
        self._rate_limit_lock = asyncio.Lock()
        self._log = log.bind(portal_id=self.portal_id, adapter_type=self.adapter_type)

    @abstractmethod
    async def fetch_catalogue(self) -> AsyncIterator[RawRecord]:
        """Yield RawRecord for each dataset in the portal catalogue."""
        ...

    @abstractmethod
    async def fetch_record(self, source_id: str) -> RawRecord:
        """Fetch a single dataset record by source_id."""
        ...

    @abstractmethod
    def get_portal_defaults(self) -> dict[str, Any]:
        """Return portal-level defaults to inject before harmonisation."""
        ...

    async def check_robots(self) -> bool:
        """
        Check robots.txt for HTML adapters. Returns True if crawling is allowed.
        Level 1 (API) adapters always return True.
        """
        if self.adapter_type != "html":
            return True
        robots_url = f"{self.base_url}/robots.txt"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(robots_url)
                if resp.status_code == 200:
                    return "Disallow: /" not in resp.text
            return True
        except Exception as e:
            self._log.warning("robots_check_failed", url=robots_url, error=str(e))
            return False  # fail safe: do not crawl if we can't check

    async def health_check(self) -> AdapterHealth:
        """Ping the base URL and return health status."""
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.head(self.base_url)
            latency_ms = (time.monotonic() - start) * 1000
            status = "healthy" if resp.status_code < 400 else "degraded"
            return AdapterHealth(
                portal_id=self.portal_id,
                status=status,
                latency_ms=latency_ms,
            )
        except Exception as e:
            return AdapterHealth(
                portal_id=self.portal_id,
                status="unhealthy",
                error_message=str(e),
            )

    async def _rate_limited_get(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> httpx.Response:
        """
        Perform a GET with rate limiting and exponential backoff retry (max 3).
        """
        async with self._rate_limit_lock:
            # Enforce rate limit
            min_interval = 1.0 / self.rate_limit_rps
            now = time.monotonic()
            wait = min_interval - (now - self._last_request_time)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_time = time.monotonic()

        for attempt in range(5):
            try:
                resp = await client.get(
                    url, params=params, headers=headers, timeout=30.0,
                    follow_redirects=True,
                )
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as e:
                if attempt == 4:
                    self._log.error("http_request_failed", url=url, error=str(e))
                    raise
                # 429: respect Retry-After or wait 30s before retrying
                if e.response.status_code == 429:
                    retry_after = int(e.response.headers.get("Retry-After", 30))
                    backoff = max(retry_after, 30)
                else:
                    backoff = 2 ** attempt
                self._log.warning(
                    "http_retry", url=url, attempt=attempt + 1, backoff=backoff, error=str(e)
                )
                await asyncio.sleep(backoff)
            except httpx.RequestError as e:
                if attempt == 4:
                    self._log.error("http_request_failed", url=url, error=str(e))
                    raise
                backoff = 2 ** attempt
                self._log.warning(
                    "http_retry", url=url, attempt=attempt + 1, backoff=backoff, error=str(e)
                )
                await asyncio.sleep(backoff)
        raise RuntimeError(f"Exhausted retries for {url}")  # unreachable

    @staticmethod
    def _hash_payload(payload: dict[str, Any]) -> str:
        """Return SHA-256 hex digest of the JSON-serialised payload."""
        serialised = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(serialised.encode("utf-8")).hexdigest()

    def _make_record(
        self, source_id: str, raw_payload: dict[str, Any]
    ) -> RawRecord:
        """Construct a RawRecord from a raw payload."""
        return RawRecord(
            source_id=source_id,
            portal_id=self.portal_id,
            raw_payload=raw_payload,
            raw_payload_hash=self._hash_payload(raw_payload),
            adapter_type=self.adapter_type,
        )
