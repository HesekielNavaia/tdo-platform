"""
Schema detector — detects the metadata schema type from a raw dict payload.
Returns one of: "SDMX" | "DCAT" | "DublinCore" | "DDI" | "WorldBank" | "unknown"
"""
from __future__ import annotations

import json
from typing import Any

from src.pipeline.mapping_tables import SCHEMA_DETECTION_SIGNALS


def detect_schema(payload: dict[str, Any]) -> str:
    """
    Scan a raw dict payload for SCHEMA_DETECTION_SIGNALS.
    Returns the first schema name that matches, or "unknown".

    Signals are matched against:
      - Top-level key names
      - Nested key paths (e.g. "data.dataflows")
      - JSON-serialised string of the whole payload (for embedded signals)
    """
    # Serialise the whole payload to a string for substring scanning
    payload_str = json.dumps(payload, ensure_ascii=False)

    scores: dict[str, int] = {schema: 0 for schema in SCHEMA_DETECTION_SIGNALS}

    for schema, signals in SCHEMA_DETECTION_SIGNALS.items():
        for signal in signals:
            if _signal_matches(signal, payload, payload_str):
                scores[schema] += 1

    # Return the schema with the highest score (if > 0)
    best_schema = max(scores, key=lambda k: scores[k])
    if scores[best_schema] > 0:
        return best_schema

    return "unknown"


def _signal_matches(signal: str, payload: dict[str, Any], payload_str: str) -> bool:
    """Check if a signal is present in the payload or its serialised form."""
    # Direct key match
    if signal in payload:
        return True

    # Dot-notation path match (e.g. "data.dataflows")
    if "." in signal:
        parts = signal.split(".")
        node: Any = payload
        for part in parts:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                node = None
                break
        if node is not None:
            return True

    # Substring match in serialised payload
    if signal in payload_str:
        return True

    return False
