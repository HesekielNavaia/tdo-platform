"""
Embedder — generates vector embeddings for MVM records.
Uses multilingual-e5-large via Azure AI Foundry serverless endpoint.
Validates embedding dimension at startup before processing any records.
"""
from __future__ import annotations

import asyncio
import structlog
from dataclasses import dataclass

import httpx

from src.models.mvm import MVMRecord

log = structlog.get_logger(__name__)


class ConfigurationError(Exception):
    """Raised when the embedding endpoint configuration is invalid."""


@dataclass
class EmbedderConfig:
    endpoint_url: str
    model_id: str = "multilingual-e5-large"
    expected_dim: int = 1024
    api_key: str | None = None
    max_retries: int = 3
    timeout_seconds: float = 30.0


class Embedder:
    def __init__(self, config: EmbedderConfig):
        self.config = config

    async def validate_config(self) -> int:
        """
        Call the endpoint with a test string and verify the returned
        dimension matches config.expected_dim.
        Raises ConfigurationError on mismatch.
        """
        test_embedding = await self._call_endpoint(["test"])
        if not test_embedding:
            raise ConfigurationError("Embedding endpoint returned no embeddings for test input")

        actual_dim = len(test_embedding[0])
        if actual_dim != self.config.expected_dim:
            raise ConfigurationError(
                f"Embedding dim mismatch: endpoint returns {actual_dim}, "
                f"config specifies {self.config.expected_dim}. "
                f"Update EMBEDDING_DIM in config and run migration if needed."
            )
        log.info(
            "embedder_config_validated",
            model=self.config.model_id,
            dim=actual_dim,
        )
        return actual_dim

    async def embed(self, record: MVMRecord) -> list[float]:
        """
        Generate an embedding for an MVM record.
        Input string: "{title} {description} {keywords} {themes} {geographic_coverage} {publisher}"
        """
        input_text = self._build_embedding_input(record)
        embeddings = await self._call_endpoint([input_text])
        if not embeddings:
            raise RuntimeError(f"No embedding returned for record {record.id}")
        return embeddings[0]

    def _build_embedding_input(self, record: MVMRecord) -> str:
        """Construct the embedding input string from MVM record fields."""
        parts = [
            record.title or "",
            record.description or "",
            " ".join(record.keywords),
            " ".join(record.themes),
            " ".join(record.geographic_coverage),
            record.publisher or "",
        ]
        return " ".join(p for p in parts if p).strip()

    async def _call_endpoint(self, texts: list[str]) -> list[list[float]]:
        """
        Call the embedding endpoint with exponential backoff (max 3 retries).
        """
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            for attempt in range(self.config.max_retries):
                try:
                    resp = await client.post(
                        self.config.endpoint_url,
                        json={"input": texts, "model": self.config.model_id},
                        headers=headers,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    # Handle OpenAI-compatible response format
                    if "data" in data:
                        return [item["embedding"] for item in data["data"]]
                    # Handle HuggingFace TEI format
                    if isinstance(data, list):
                        return data
                    raise RuntimeError(f"Unexpected embedding response format: {list(data.keys())}")
                except httpx.HTTPStatusError as e:
                    if attempt == self.config.max_retries - 1:
                        log.error("embed_http_error", status=e.response.status_code, error=str(e))
                        raise
                    await asyncio.sleep(2 ** attempt)
                except Exception as e:
                    if attempt == self.config.max_retries - 1:
                        log.error("embed_error", error=str(e))
                        raise
                    await asyncio.sleep(2 ** attempt)
        return []
