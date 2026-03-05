"""
Harmoniser — converts raw portal records to MVMRecord.
Deterministic mapping first, then Phi-4 LLM for unmapped fields,
Azure OpenAI fallback for confidence < 0.3.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import structlog

from src.models.mvm import MVMRecord
from src.pipeline.mapping_tables import (
    SCHEMA_TO_MAPPING,
    PORTAL_DEFAULTS,
    LLM_ONLY_FIELDS,
    NULLABLE_FIELDS,
    SDMX_AGENCY_NAMES,
    _frequency_map,
    _iso_date,
)
from src.pipeline.schema_detector import detect_schema

log = structlog.get_logger(__name__)

HARMONISER_VERSION = "0.1.0"

# Fields that the LLM must never populate by invention
NEVER_INVENT = {"dataset_url", "publisher", "license",
                "temporal_coverage_start", "temporal_coverage_end"}

# Recommended fields for completeness scoring
RECOMMENDED_FIELDS = {
    "title", "description", "publisher", "geographic_coverage",
    "temporal_coverage_start", "update_frequency", "last_updated",
    "access_type", "license", "formats", "keywords"
}

# LLM confidence weights per field
FIELD_WEIGHTS = {
    "title": 0.20,
    "description": 0.15,
    "publisher": 0.15,
    "geographic_coverage": 0.10,
    "temporal_coverage_start": 0.05,
    "temporal_coverage_end": 0.05,
    "update_frequency": 0.05,
    "last_updated": 0.05,
    "access_type": 0.05,
    "license": 0.05,
    "keywords": 0.05,
    "themes": 0.05,
}
DEFAULT_WEIGHT = 0.05

LLM_SYSTEM_PROMPT = """You are a metadata harmonisation specialist for official statistical data.
Your task is to extract specific fields from a raw metadata record and map
them to the provided JSON schema.

Rules you must follow without exception:
1. Only populate a field if you can identify WHERE in the raw payload the
   value comes from. For each field you populate, include the source path
   in field_evidence.
2. Never invent or infer: URLs, publisher names, license identifiers, or
   dates. If not present in the raw payload, return null for that field.
3. Return only valid JSON matching the target schema.
4. Set field_confidence for each field you populate (0.0–1.0).
5. Set overall confidence_score as the mean of field_confidence values,
   weighted by field importance (title=0.2, description=0.15,
   publisher=0.15, geographic_coverage=0.1, temporal=0.1, rest=0.05 each)."""

DESCRIPTION_EXTRACT_PROMPT = """You are a metadata analyst specialising in official statistical datasets.
Extract the following fields from the dataset description text provided.
Return ONLY valid JSON. Do not include any preamble or explanation.

Fields to extract:
- time_series_length: human-readable length/span of the time series (e.g. "50 years", "1970–2023"); null if not mentioned
- methodology_url: a URL pointing to methodology documentation, if explicitly stated in the text; null otherwise
- related_datasets: list of dataset names or identifiers explicitly mentioned as related/linked; [] if none
- subject_classification: list of subject areas, topics, or statistical domains mentioned (e.g. ["labour market", "employment"]);  [] if none
- unit_of_measure: the unit used for observations (e.g. "persons", "EUR millions", "index points"); null if not stated
- observation_count_estimate: integer estimate of total observations/data points if mentioned (e.g. 15000); null if not mentioned
- field_confidence: object mapping each field name to a confidence score 0.0–1.0 reflecting how clearly it is stated

Rules:
- Only extract from the text provided — do not invent values.
- methodology_url must be a syntactically valid URL or null.
- observation_count_estimate must be an integer or null."""

# Description-derived fields with their DB/MVM field names
DESCRIPTION_DERIVED_FIELDS = {
    "time_series_length",
    "methodology_url",
    "related_datasets",
    "subject_classification",
    "unit_of_measure",
    "observation_count_estimate",
}


class HarmoniserConfig:
    def __init__(
        self,
        phi4_endpoint: str | None = None,
        phi4_api_key: str | None = None,
        openai_endpoint: str | None = None,
        openai_api_key: str | None = None,
        openai_model: str = "gpt-4o",
        low_confidence_threshold: float = 0.3,
        review_threshold: float = 0.6,
        embedding_dim: int = 1024,
    ):
        self.phi4_endpoint = phi4_endpoint
        self.phi4_api_key = phi4_api_key
        self.openai_endpoint = openai_endpoint
        self.openai_api_key = openai_api_key
        self.openai_model = openai_model
        self.low_confidence_threshold = low_confidence_threshold
        self.review_threshold = review_threshold
        self.embedding_dim = embedding_dim


class Harmoniser:
    def __init__(self, config: HarmoniserConfig | None = None):
        self.config = config or HarmoniserConfig()

    async def process(
        self,
        raw_payload: dict[str, Any],
        portal_id: str,
        source_id: str | None = None,
    ) -> tuple[MVMRecord, dict[str, Any]]:
        """
        Process a raw payload into an MVMRecord.
        Returns (mvm_record, processing_metadata).
        Catches Pydantic validation errors — logs them, does not re-raise.
        """
        log.bind(portal_id=portal_id, source_id=source_id, stage="harmonise")

        # Inject portal defaults
        defaults = PORTAL_DEFAULTS.get(portal_id, {})
        enriched = {**defaults, **raw_payload}

        # Detect schema
        schema_type = detect_schema(enriched)
        if schema_type == "unknown":
            schema_type = defaults.get("_schema_detected", "unknown")

        # Apply deterministic mapping
        mapped, field_evidence, field_confidence = self._apply_deterministic_mapping(
            enriched, schema_type
        )

        # Identify unmapped fields
        all_mvm_fields = set(MVMRecord.model_fields.keys())
        already_mapped = {k for k, v in mapped.items() if v is not None and v != [] and v != ""}
        unmapped = all_mvm_fields - already_mapped - {
            "id", "source_id", "source_id_aliases", "ingestion_timestamp",
            "confidence_score", "completeness_score", "freshness_score", "link_healthy"
        }

        # LLM path for unmapped fields (only if endpoint configured)
        llm_model_used = None
        llm_fallback_triggered = False

        if unmapped and self.config.phi4_endpoint:
            llm_result, llm_evidence, llm_confidence = await self._call_llm(
                raw_payload=raw_payload,
                schema_type=schema_type,
                portal_id=portal_id,
                already_mapped=already_mapped,
                unmapped_fields=unmapped,
                endpoint=self.config.phi4_endpoint,
                api_key=self.config.phi4_api_key,
                model="phi-4",
            )
            llm_model_used = "phi-4"
            for field, value in llm_result.items():
                if field not in mapped or mapped[field] is None:
                    # LLM must not invent restricted fields
                    if field in NEVER_INVENT and value is not None:
                        # Only accept if evidence exists
                        evidence = llm_evidence.get(field)
                        if not evidence:
                            continue
                    mapped[field] = value
            field_evidence.update(llm_evidence)
            field_confidence.update(llm_confidence)

        # Calculate overall confidence
        confidence = self._calc_confidence(field_confidence)

        # If very low confidence, try OpenAI fallback
        if confidence < self.config.low_confidence_threshold and self.config.openai_endpoint:
            llm_fallback_triggered = True
            fallback_result, fallback_evidence, fallback_confidence = await self._call_llm(
                raw_payload=raw_payload,
                schema_type=schema_type,
                portal_id=portal_id,
                already_mapped=already_mapped,
                unmapped_fields=unmapped,
                endpoint=self.config.openai_endpoint,
                api_key=self.config.openai_api_key,
                model=self.config.openai_model,
            )
            llm_model_used = f"phi-4+{self.config.openai_model}"
            for field, value in fallback_result.items():
                if field not in mapped or mapped[field] is None:
                    if field in NEVER_INVENT and value is not None:
                        evidence = fallback_evidence.get(field)
                        if not evidence:
                            continue
                    mapped[field] = value
            field_evidence.update(fallback_evidence)
            field_confidence.update(fallback_confidence)
            confidence = self._calc_confidence(field_confidence)

        # Extract additional fields from description text via LLM
        desc_extracted: dict[str, Any] = {}
        desc_confidences: dict[str, float] = {}
        description_text = mapped.get("description")
        if description_text and (self.config.phi4_endpoint or self.config.openai_endpoint):
            endpoint = self.config.phi4_endpoint or self.config.openai_endpoint
            api_key = self.config.phi4_api_key if self.config.phi4_endpoint else self.config.openai_api_key
            model = "phi-4" if self.config.phi4_endpoint else self.config.openai_model
            desc_extracted, desc_confidences = await self._extract_from_description(
                description_text, endpoint, api_key, model
            )
            field_confidence.update({
                f"{k}_confidence": v for k, v in desc_confidences.items()
            })

        # Compute freshness (doesn't depend on portal defaults)
        freshness = self._calc_freshness(
            mapped.get("last_updated"), mapped.get("update_frequency")
        )

        # Build the MVM record
        record_id = str(uuid4())
        try:
            mvm = MVMRecord(
                id=record_id,
                source_id=source_id or mapped.get("id", record_id),
                source_id_aliases=[],
                resource_type=mapped.get("resource_type", "dataset"),
                title=mapped.get("title") or "Untitled",
                description=mapped.get("description"),
                publisher=mapped.get("publisher") or defaults.get("_publisher", "Unknown"),
                publisher_type=mapped.get("publisher_type") or defaults.get("_publisher_type", "other"),
                source_portal=mapped.get("source_portal") or defaults.get("_source_portal", ""),
                dataset_url=mapped.get("dataset_url"),
                keywords=mapped.get("keywords") or [],
                themes=mapped.get("themes") or [],
                geographic_coverage=mapped.get("geographic_coverage") or [],
                temporal_coverage_start=mapped.get("temporal_coverage_start"),
                temporal_coverage_end=mapped.get("temporal_coverage_end"),
                languages=mapped.get("languages") or defaults.get("_languages", []),
                update_frequency=mapped.get("update_frequency"),
                last_updated=mapped.get("last_updated"),
                access_type=mapped.get("access_type") or defaults.get("_access_type", "open"),
                access_conditions=mapped.get("access_conditions"),
                license=mapped.get("license") or defaults.get("_license"),
                formats=mapped.get("formats") or defaults.get("_formats", []),
                contact_point=mapped.get("contact_point"),
                provenance=mapped.get("provenance"),
                metadata_standard=schema_type if schema_type in (
                    "SDMX", "DCAT", "DublinCore", "DDI"
                ) else "unknown",
                # LLM-extracted from description
                time_series_length=desc_extracted.get("time_series_length"),
                time_series_length_confidence=desc_confidences.get("time_series_length"),
                methodology_url=desc_extracted.get("methodology_url"),
                methodology_url_confidence=desc_confidences.get("methodology_url"),
                related_datasets=desc_extracted.get("related_datasets") or [],
                related_datasets_confidence=desc_confidences.get("related_datasets"),
                subject_classification=desc_extracted.get("subject_classification") or [],
                subject_classification_confidence=desc_confidences.get("subject_classification"),
                unit_of_measure=desc_extracted.get("unit_of_measure"),
                unit_of_measure_confidence=desc_confidences.get("unit_of_measure"),
                observation_count_estimate=desc_extracted.get("observation_count_estimate"),
                observation_count_estimate_confidence=desc_confidences.get("observation_count_estimate"),
                confidence_score=round(min(1.0, max(0.0, confidence)), 4),
                completeness_score=0.0,  # calculated below from actual record values
                freshness_score=round(min(1.0, max(0.0, freshness)), 4),
                link_healthy=None,
                ingestion_timestamp=datetime.now(timezone.utc),
            )
        except Exception as exc:
            log.error("pydantic_validation_error", error=str(exc))
            # Build a minimal record to avoid data loss
            mvm = MVMRecord(
                id=record_id,
                source_id=source_id or record_id,
                title="Validation Error — see processing record",
                publisher=defaults.get("_publisher", "Unknown"),
                publisher_type=defaults.get("_publisher_type", "other"),
                source_portal=defaults.get("_source_portal", ""),
                access_type=defaults.get("_access_type", "open"),
                metadata_standard="unknown",
                confidence_score=0.0,
                completeness_score=0.0,
                freshness_score=0.0,
                ingestion_timestamp=datetime.now(timezone.utc),
            )
            confidence = 0.0

        # Compute completeness from the fully-resolved record (after portal defaults applied)
        completeness = self._calc_completeness({
            "title":                    None if mvm.title in ("Untitled", "Validation Error — see processing record") else mvm.title,
            "description":              mvm.description,
            "publisher":                None if mvm.publisher == "Unknown" else mvm.publisher,
            "geographic_coverage":      mvm.geographic_coverage,
            "temporal_coverage_start":  mvm.temporal_coverage_start,
            "update_frequency":         mvm.update_frequency,
            "last_updated":             mvm.last_updated,
            "access_type":              mvm.access_type,
            "license":                  mvm.license,
            "formats":                  mvm.formats,
            "keywords":                 mvm.keywords,
        })
        mvm = mvm.model_copy(update={"completeness_score": round(min(1.0, max(0.0, completeness)), 4)})

        # Flag for review if confidence is below threshold
        flagged = mvm.confidence_score < self.config.review_threshold
        review_reason = (
            f"confidence_score={mvm.confidence_score:.2f} < {self.config.review_threshold}"
            if flagged else None
        )

        processing_meta = {
            "field_confidence": field_confidence,
            "field_evidence": field_evidence,
            "llm_model_used": llm_model_used,
            "llm_fallback_triggered": llm_fallback_triggered,
            "flagged_for_review": flagged,
            "review_reason": review_reason,
            "harmoniser_version": HARMONISER_VERSION,
        }

        return mvm, processing_meta

    def _apply_deterministic_mapping(
        self,
        payload: dict[str, Any],
        schema_type: str,
    ) -> tuple[dict[str, Any], dict[str, str], dict[str, float]]:
        """Apply deterministic field mapping tables to the payload."""
        mapping = SCHEMA_TO_MAPPING.get(schema_type, {})
        result: dict[str, Any] = {}
        field_evidence: dict[str, str] = {}
        field_confidence: dict[str, float] = {}

        for source_path, (mvm_field, transform) in mapping.items():
            value = self._extract_path(payload, source_path)
            if value is None:
                continue
            if transform is not None:
                try:
                    value = transform(value)
                except Exception:
                    continue
            if value is None or value == "" or value == []:
                continue
            # Only set if not already set (first mapping wins)
            if mvm_field not in result or result[mvm_field] is None:
                result[mvm_field] = value
                field_evidence[mvm_field] = source_path
                field_confidence[mvm_field] = 1.0  # deterministic = full confidence

        # Resolve SDMX agency IDs to human-readable publisher names
        if "publisher" in result and result["publisher"] in SDMX_AGENCY_NAMES:
            result["publisher"] = SDMX_AGENCY_NAMES[result["publisher"]]

        return result, field_evidence, field_confidence

    def _extract_path(self, payload: dict[str, Any], path: str) -> Any:
        """Extract a value from a nested dict using dot-notation path."""
        # Handle underscore-prefixed injected fields
        if path.startswith("_"):
            return payload.get(path)

        parts = path.split(".")
        node: Any = payload
        for part in parts:
            if part.endswith("]"):
                # Array indexing like [0] or [*]
                bracket_idx = part.index("[")
                key = part[:bracket_idx]
                idx_str = part[bracket_idx + 1:-1]
                if isinstance(node, dict):
                    node = node.get(key)
                else:
                    return None
                if isinstance(node, list):
                    if idx_str == "*":
                        return node  # return whole list
                    try:
                        node = node[int(idx_str)]
                    except (IndexError, ValueError):
                        return None
            else:
                if isinstance(node, dict):
                    node = node.get(part)
                else:
                    return None
        return node

    async def _call_llm(
        self,
        raw_payload: dict[str, Any],
        schema_type: str,
        portal_id: str,
        already_mapped: set[str],
        unmapped_fields: set[str],
        endpoint: str,
        api_key: str | None,
        model: str,
    ) -> tuple[dict[str, Any], dict[str, str], dict[str, float]]:
        """
        Call an LLM endpoint for field extraction.
        Returns (result_dict, field_evidence, field_confidence).
        On error: returns empty dicts.
        """
        try:
            import httpx

            user_prompt = (
                f"Source schema: {schema_type}\n"
                f"Portal: {portal_id}\n\n"
                f"Raw metadata payload:\n{json.dumps(raw_payload, indent=2)}\n\n"
                f"Fields already populated by deterministic mapping (do not re-populate):\n"
                f"{json.dumps(list(already_mapped))}\n\n"
                f"Fields requiring extraction:\n{json.dumps(list(unmapped_fields))}\n\n"
                f"Return JSON only. No preamble."
            )

            messages = [
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]

            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            async with httpx.AsyncClient(timeout=30.0) as client:
                for attempt in range(3):
                    try:
                        resp = await client.post(
                            endpoint,
                            json={"model": model, "messages": messages},
                            headers=headers,
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        content = data["choices"][0]["message"]["content"]
                        parsed = json.loads(content)
                        field_confidence = parsed.pop("field_confidence", {})
                        field_evidence = parsed.pop("field_evidence", {})
                        # Strip never-invent fields without evidence
                        for field in list(NEVER_INVENT):
                            if field in parsed and not field_evidence.get(field):
                                del parsed[field]
                        return parsed, field_evidence, field_confidence
                    except Exception as e:
                        if attempt == 2:
                            log.error("llm_call_failed", model=model, error=str(e))
                            return {}, {}, {}
                        import asyncio
                        await asyncio.sleep(2 ** attempt)
        except Exception as e:
            log.error("llm_call_error", model=model, error=str(e))
        return {}, {}, {}

    async def _extract_from_description(
        self,
        description: str,
        endpoint: str,
        api_key: str | None,
        model: str,
    ) -> tuple[dict[str, Any], dict[str, float]]:
        """
        Call LLM to extract DESCRIPTION_DERIVED_FIELDS from description text.
        Returns (extracted_values, field_confidences).
        """
        try:
            import httpx

            messages = [
                {"role": "system", "content": DESCRIPTION_EXTRACT_PROMPT},
                {"role": "user", "content": f"Dataset description:\n\n{description}"},
            ]
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            async with httpx.AsyncClient(timeout=30.0) as client:
                for attempt in range(3):
                    try:
                        resp = await client.post(
                            endpoint,
                            json={"model": model, "messages": messages},
                            headers=headers,
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        content = data["choices"][0]["message"]["content"]
                        parsed = json.loads(content)
                        confidences: dict[str, float] = parsed.pop("field_confidence", {})
                        # Keep only expected fields; coerce types
                        result: dict[str, Any] = {}
                        for field in DESCRIPTION_DERIVED_FIELDS:
                            val = parsed.get(field)
                            if field == "observation_count_estimate" and val is not None:
                                try:
                                    val = int(val)
                                except (ValueError, TypeError):
                                    val = None
                            if field in ("related_datasets", "subject_classification"):
                                result[field] = val if isinstance(val, list) else []
                            else:
                                result[field] = val
                        return result, {k: float(v) for k, v in confidences.items() if k in DESCRIPTION_DERIVED_FIELDS}
                    except Exception as e:
                        if attempt == 2:
                            log.error("description_extract_failed", model=model, error=str(e))
                            return {}, {}
                        import asyncio
                        await asyncio.sleep(2 ** attempt)
        except Exception as e:
            log.error("description_extract_error", model=model, error=str(e))
        return {}, {}

    def _calc_confidence(self, field_confidence: dict[str, float]) -> float:
        """Weighted confidence score from per-field confidences."""
        if not field_confidence:
            return 0.0
        total_weight = 0.0
        weighted_sum = 0.0
        for field, score in field_confidence.items():
            weight = FIELD_WEIGHTS.get(field, DEFAULT_WEIGHT)
            weighted_sum += score * weight
            total_weight += weight
        if total_weight == 0:
            return 0.0
        return weighted_sum / total_weight

    def _calc_completeness(self, mapped: dict[str, Any]) -> float:
        """Fraction of recommended fields that are populated."""
        populated = sum(
            1 for f in RECOMMENDED_FIELDS
            if mapped.get(f) not in (None, [], "")
        )
        return populated / len(RECOMMENDED_FIELDS)

    def _calc_freshness(
        self, last_updated: str | None, update_frequency: str | None
    ) -> float:
        """1.0 = updated within expected frequency window."""
        if not last_updated or not update_frequency:
            return 0.5
        freq_days = {
            "daily": 1, "weekly": 7, "monthly": 31, "annual": 366, "irregular": 730
        }
        expected = freq_days.get(update_frequency, 730)
        try:
            last = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - last).days
            return max(0.0, 1.0 - (age_days / (expected * 2)))
        except (ValueError, TypeError):
            return 0.5
