"""
Deterministic metadata mapping tables: SDMX, DCAT, Dublin Core, DDI → MVM
Trusted Data Observatory — Phase 1

These mappings cover the common fields returned by the five target portals:
  - Statistics Finland (SDMX / PX-Web)
  - Eurostat (SDMX REST 2.1)
  - World Bank (JSON / DCAT-like)
  - OECD (SDMX REST 2.1)
  - UN Data (SDMX)

Each mapping is a dict of:
    { source_field_path: mvm_field }

Where source_field_path uses dot notation for nested fields and
[*] for list iteration.

Fields NOT covered by deterministic mapping fall through to the
Phi-4 LLM harmonisation stage.

Author: TDO pipeline team
Python: 3.12
"""

from __future__ import annotations
from typing import Any, Callable
import re


# ---------------------------------------------------------------------------
# HELPER TRANSFORMS
# Applied to source values before writing to MVM field.
# ---------------------------------------------------------------------------

def _first(val: Any) -> Any:
    """Return first element if list, else value as-is."""
    if isinstance(val, list) and val:
        return val[0]
    return val

def _join(sep: str = ", ") -> Callable:
    def _fn(val: Any) -> str | None:
        if isinstance(val, list):
            return sep.join(str(v) for v in val if v)
        return str(val) if val else None
    return _fn

def _lower(val: Any) -> str | None:
    return str(val).lower().strip() if val else None

def _strip(val: Any) -> str | None:
    return str(val).strip() if val else None

def _iso_date(val: Any) -> str | None:
    """Normalise common date formats to YYYY-MM-DD or YYYY."""
    if not val:
        return None
    s = str(val).strip()
    # Already ISO
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    # Year only
    if re.match(r"^\d{4}$", s):
        return s
    # YYYYMM
    if re.match(r"^\d{6}$", s):
        return f"{s[:4]}-{s[4:6]}"
    # DD/MM/YYYY or MM/DD/YYYY — return YYYY only to be safe
    if re.match(r"^\d{2}/\d{2}/\d{4}$", s):
        return s[-4:]
    return s  # return raw if unrecognised; LLM will clean up

def _frequency_map(val: Any) -> str | None:
    """Map SDMX FREQ codes and plain text to MVM update_frequency."""
    if not val:
        return None
    mapping = {
        # SDMX FREQ codes
        "A":   "annual",
        "S":   "annual",       # semi-annual → annual tier
        "Q":   "annual",       # quarterly → annual tier
        "M":   "monthly",
        "W":   "weekly",
        "D":   "daily",
        "H":   "annual",       # half-yearly
        "N":   "irregular",    # minutely/real-time
        "B":   "irregular",    # business days
        # Plain text variants
        "annual":      "annual",
        "yearly":      "annual",
        "quarterly":   "annual",
        "monthly":     "monthly",
        "weekly":      "weekly",
        "daily":       "daily",
        "irregular":   "irregular",
        "unknown":     "irregular",
        "other":       "irregular",
    }
    return mapping.get(str(val).strip().upper(),
           mapping.get(str(val).strip().lower(), "irregular"))

def _access_map(val: Any) -> str | None:
    """Map licence/access strings to open | restricted | embargoed."""
    if not val:
        return None
    s = str(val).lower()
    if any(k in s for k in ["open", "public", "cc", "odc", "mit", "apache"]):
        return "open"
    if any(k in s for k in ["embarg", "forthcoming"]):
        return "embargoed"
    if any(k in s for k in ["restricted", "confidential", "request",
                              "subscription", "license required"]):
        return "restricted"
    return "open"  # assume open for official stat portals unless stated

def _languages_list(val: Any) -> list[str]:
    """Normalise language codes to list of ISO 639-1 codes."""
    lang_map = {
        "english": "en", "finnish": "fi", "swedish": "sv",
        "french": "fr", "german": "de", "spanish": "es",
        "italian": "it", "portuguese": "pt", "arabic": "ar",
        "chinese": "zh", "russian": "ru", "japanese": "ja",
    }
    if isinstance(val, list):
        raw = val
    elif isinstance(val, str):
        raw = [v.strip() for v in val.replace(";", ",").split(",")]
    else:
        return []
    result = []
    for v in raw:
        v_lower = v.lower()
        result.append(lang_map.get(v_lower, v_lower[:2] if len(v_lower) >= 2 else v_lower))
    return list(dict.fromkeys(result))  # deduplicate, preserve order


# ---------------------------------------------------------------------------
# 1. SDMX → MVM
# Covers: Eurostat, Statistics Finland, OECD, UN Data
#
# Source structure follows SDMX 2.1 Structure Message / Data Structure
# Definition (DSD) as returned by REST API in JSON (structure-specific-json
# format) or parsed from XML.
#
# Key paths assume the common SDMX JSON format:
#   data.dataflows[0].name.en
#   data.dataflows[0].description.en
#   etc.
# ---------------------------------------------------------------------------

SDMX_TO_MVM: dict[str, tuple[str, Callable | None]] = {
    # --- Identity ---
    "data.dataflows[0].urn":                ("id",                   _strip),
    "data.dataflows[0].id":                 ("id",                   _strip),   # fallback

    # --- Title (prefer English, fall back to first available) ---
    "data.dataflows[0].name.en":            ("title",                _strip),
    "data.dataflows[0].name.fr":            ("title",                _strip),   # fallback
    "data.dataflows[0].name":               ("title",                _strip),   # fallback (string)

    # --- Description ---
    "data.dataflows[0].description.en":     ("description",          _strip),
    "data.dataflows[0].description.fr":     ("description",          _strip),
    "data.dataflows[0].description":        ("description",          _strip),

    # --- Publisher (from dataflows agency or structure agency) ---
    "data.dataflows[0].agencyID":           ("publisher",            _strip),
    "data.structures[0].agencyID":          ("publisher",            _strip),

    # --- Keywords / subjects ---
    "data.dataflows[0].annotations[*].text.en": ("keywords",         None),   # list passthrough

    # --- Temporal ---
    "data.dataflows[0].validFrom":          ("temporal_coverage_start", _iso_date),
    "data.dataflows[0].validTo":            ("temporal_coverage_end",   _iso_date),

    # --- Frequency (from DSD dimension FREQ) ---
    "data.dimensions[0].values[FREQ].id":   ("update_frequency",    _frequency_map),
    "data.attributes[FREQ].values[0].id":   ("update_frequency",    _frequency_map),

    # --- Geographic coverage (from DSD dimension REF_AREA) ---
    "data.dimensions[0].values[REF_AREA]":  ("geographic_coverage", None),   # list passthrough
    "data.attributes[REF_AREA].values":     ("geographic_coverage", None),

    # --- Last updated ---
    "data.dataflows[0].annotations[UPDATE].text": ("last_updated",  _iso_date),
    "meta.prepared":                        ("last_updated",         _iso_date),

    # --- Access ---
    "data.dataflows[0].annotations[ACCESS_TYPE].text": ("access_type", _access_map),

    # --- Formats ---
    # SDMX portals serve SDMX by definition; formats added by crawler
    # from portal capability response
    "_portal_formats":                      ("formats",              None),

    # --- Metadata standard ---
    "_schema_detected":                     ("metadata_standard",    lambda _: "SDMX"),

    # --- Source portal (injected by crawler) ---
    "_source_portal":                       ("source_portal",        _strip),
    "_dataset_url":                         ("dataset_url",          _strip),
    "_publisher_type":                      ("publisher_type",        _strip),
}


# ---------------------------------------------------------------------------
# SDMX AGENCY ID → human-readable publisher name
# Used to enrich publisher field post-mapping.
# ---------------------------------------------------------------------------

SDMX_AGENCY_NAMES: dict[str, str] = {
    "ESTAT":    "Eurostat",
    "OECD":     "OECD",
    "UNSD":     "United Nations Statistics Division",
    "UNECE":    "United Nations Economic Commission for Europe",
    "IMF":      "International Monetary Fund",
    "WB":       "World Bank",
    "ECB":      "European Central Bank",
    "ILO":      "International Labour Organization",
    "WHO":      "World Health Organization",
    "FAO":      "Food and Agriculture Organization",
    "UNESCO":   "UNESCO",
    "UNICEF":   "UNICEF",
    "STATFIN":  "Statistics Finland",
    "SF":       "Statistics Finland",
}


# ---------------------------------------------------------------------------
# 2. DCAT → MVM
# Covers: World Bank (uses DCAT-AP variant in its API responses),
# any portal exposing a DCAT catalogue.
#
# Source paths follow DCAT-AP 2.1 (W3C) as serialised in JSON-LD or
# as parsed from Turtle/RDF.
# ---------------------------------------------------------------------------

DCAT_TO_MVM: dict[str, tuple[str, Callable | None]] = {
    # --- Identity ---
    "@id":                                  ("id",                   _strip),
    "dct:identifier":                       ("id",                   _strip),

    # --- Title ---
    "dct:title":                            ("title",                _strip),
    "rdfs:label":                           ("title",                _strip),

    # --- Description ---
    "dct:description":                      ("description",          _strip),
    "schema:description":                   ("description",          _strip),

    # --- Publisher ---
    "dct:publisher.foaf:name":              ("publisher",            _strip),
    "dct:publisher.@id":                    ("publisher",            _strip),
    "schema:publisher.schema:name":         ("publisher",            _strip),

    # --- Keywords ---
    "dcat:keyword":                         ("keywords",             None),   # list
    "dct:subject":                          ("keywords",             None),

    # --- Themes ---
    "dcat:theme":                           ("themes",               None),   # list of URIs
    "dct:subject":                          ("themes",               None),

    # --- Geographic coverage ---
    "dct:spatial.rdfs:label":              ("geographic_coverage",   None),
    "dct:spatial":                          ("geographic_coverage",  None),
    "schema:spatialCoverage":              ("geographic_coverage",   None),

    # --- Temporal ---
    "dct:temporal.schema:startDate":       ("temporal_coverage_start", _iso_date),
    "dct:temporal.schema:endDate":         ("temporal_coverage_end",   _iso_date),
    "dct:temporal.dcat:startDate":         ("temporal_coverage_start", _iso_date),
    "dct:temporal.dcat:endDate":           ("temporal_coverage_end",   _iso_date),

    # --- Frequency ---
    "dct:accrualPeriodicity":              ("update_frequency",      _frequency_map),
    "schema:measurementTechnique":         ("update_frequency",      _frequency_map),

    # --- Last updated ---
    "dct:modified":                        ("last_updated",          _iso_date),
    "schema:dateModified":                 ("last_updated",          _iso_date),

    # --- Access & licence ---
    "dct:accessRights.rdfs:label":         ("access_conditions",     _strip),
    "dct:accessRights":                    ("access_type",           _access_map),
    "dct:license":                         ("license",               _strip),
    "schema:license":                      ("license",               _strip),

    # --- Formats ---
    "dcat:distribution[*].dct:format":     ("formats",               None),   # list
    "dcat:distribution[*].dcat:mediaType": ("formats",               None),

    # --- Dataset URL ---
    "dcat:landingPage":                    ("dataset_url",            _strip),
    "schema:url":                          ("dataset_url",            _strip),

    # --- Languages ---
    "dct:language":                        ("languages",              _languages_list),

    # --- Contact ---
    "dcat:contactPoint.vcard:hasEmail":    ("contact_point",          _strip),
    "dcat:contactPoint.vcard:hasURL":      ("contact_point",          _strip),

    # --- Provenance ---
    "dct:provenance.rdfs:label":           ("provenance",             _strip),
    "dct:source":                          ("provenance",             _strip),

    # --- Metadata standard ---
    "_schema_detected":                    ("metadata_standard",      lambda _: "DCAT"),

    # --- Injected by crawler ---
    "_source_portal":                      ("source_portal",          _strip),
    "_publisher_type":                     ("publisher_type",          _strip),
}


# ---------------------------------------------------------------------------
# 3. DUBLIN CORE → MVM
# Covers: legacy portals, some UN agency catalogues, HTML meta tags.
# Dublin Core is minimal — expect high LLM fallback rate for this schema.
# ---------------------------------------------------------------------------

DUBLIN_CORE_TO_MVM: dict[str, tuple[str, Callable | None]] = {
    # --- Identity ---
    "dc:identifier":                        ("id",                   _strip),
    "dcterms:identifier":                   ("id",                   _strip),

    # --- Title ---
    "dc:title":                             ("title",                _strip),
    "dcterms:title":                        ("title",                _strip),

    # --- Description ---
    "dc:description":                       ("description",          _strip),
    "dcterms:description":                  ("description",          _strip),
    "dc:abstract":                          ("description",          _strip),

    # --- Publisher ---
    "dc:publisher":                         ("publisher",            _strip),
    "dcterms:publisher":                    ("publisher",            _strip),

    # --- Keywords / subjects ---
    "dc:subject":                           ("keywords",             None),
    "dcterms:subject":                      ("keywords",             None),

    # --- Geographic coverage ---
    "dcterms:spatial":                      ("geographic_coverage",  None),
    "dc:coverage":                          ("geographic_coverage",  None),

    # --- Temporal ---
    "dcterms:temporal":                     ("temporal_coverage_start", _iso_date),
    "dc:date":                              ("last_updated",          _iso_date),
    "dcterms:created":                      ("temporal_coverage_start", _iso_date),
    "dcterms:modified":                     ("last_updated",          _iso_date),
    "dcterms:issued":                       ("temporal_coverage_start", _iso_date),

    # --- Licence ---
    "dc:rights":                            ("access_conditions",    _strip),
    "dcterms:license":                      ("license",              _strip),
    "dcterms:rights":                       ("access_conditions",    _strip),
    "dcterms:accessRights":                 ("access_type",          _access_map),

    # --- Language ---
    "dc:language":                          ("languages",            _languages_list),
    "dcterms:language":                     ("languages",            _languages_list),

    # --- Format ---
    "dc:format":                            ("formats",              None),
    "dcterms:format":                       ("formats",              None),

    # --- Source / provenance ---
    "dc:source":                            ("provenance",           _strip),
    "dcterms:source":                       ("provenance",           _strip),

    # --- Relation (can contain dataset URL) ---
    "dc:relation":                          ("dataset_url",          _strip),

    # --- Metadata standard ---
    "_schema_detected":                     ("metadata_standard",    lambda _: "DublinCore"),

    # --- Injected by crawler ---
    "_source_portal":                       ("source_portal",        _strip),
    "_publisher_type":                      ("publisher_type",       _strip),
}


# ---------------------------------------------------------------------------
# 4. DDI (Data Documentation Initiative) → MVM
# Covers: some national statistical offices, microdata catalogues.
# DDI Codebook 2.5 / DDI Lifecycle 3.x field paths.
# ---------------------------------------------------------------------------

DDI_TO_MVM: dict[str, tuple[str, Callable | None]] = {
    # --- Identity ---
    "stdyDscr.citation.titlStmt.IDNo":      ("id",                   _strip),
    "stdyDscr.citation.titlStmt.IDNo[@agency]": ("id",              _strip),

    # --- Title ---
    "stdyDscr.citation.titlStmt.titl":      ("title",               _strip),
    "stdyDscr.citation.titlStmt.parTitl":   ("title",               _strip),

    # --- Description / abstract ---
    "stdyDscr.stdyInfo.abstract":           ("description",         _strip),
    "stdyDscr.stdyInfo.sumDscr.anlyUnit":   ("description",         _strip),

    # --- Publisher / distributor ---
    "stdyDscr.citation.distStmt.distrbtr":  ("publisher",           _strip),
    "stdyDscr.citation.prodStmt.producer":  ("publisher",           _strip),

    # --- Keywords ---
    "stdyDscr.stdyInfo.subject.keyword":    ("keywords",            None),
    "stdyDscr.stdyInfo.subject.topcClas":   ("themes",              None),

    # --- Geographic coverage ---
    "stdyDscr.stdyInfo.sumDscr.nation":     ("geographic_coverage", None),
    "stdyDscr.stdyInfo.sumDscr.geogCover":  ("geographic_coverage", None),

    # --- Temporal ---
    "stdyDscr.stdyInfo.sumDscr.collDate[@event=start]": ("temporal_coverage_start", _iso_date),
    "stdyDscr.stdyInfo.sumDscr.collDate[@event=end]":   ("temporal_coverage_end",   _iso_date),

    # --- Frequency ---
    "stdyDscr.stdyInfo.sumDscr.dataKind":   ("update_frequency",   _frequency_map),

    # --- Last updated ---
    "stdyDscr.citation.prodStmt.prodDate":  ("last_updated",        _iso_date),
    "stdyDscr.citation.verStmt.version[@date]": ("last_updated",    _iso_date),

    # --- Licence / access ---
    "stdyDscr.dataAccs.useStmt.conditions": ("access_conditions",   _strip),
    "stdyDscr.dataAccs.useStmt.restrctn":   ("access_type",         _access_map),
    "stdyDscr.dataAccs.useStmt.specPerm":   ("license",             _strip),

    # --- Language ---
    "stdyDscr.citation.titlStmt.titl[@xml:lang]": ("languages",    _languages_list),

    # --- Contact ---
    "stdyDscr.citation.distStmt.contact":   ("contact_point",       _strip),

    # --- Provenance ---
    "stdyDscr.method.dataColl.sources.dataSrc": ("provenance",      _strip),

    # --- Metadata standard ---
    "_schema_detected":                     ("metadata_standard",   lambda _: "DDI"),

    # --- Injected by crawler ---
    "_source_portal":                       ("source_portal",       _strip),
    "_publisher_type":                      ("publisher_type",      _strip),
}


# ---------------------------------------------------------------------------
# 5. WORLD BANK JSON API → MVM
# World Bank uses its own REST JSON format (not strict DCAT).
# Endpoint: https://api.worldbank.org/v2/sources?format=json
# ---------------------------------------------------------------------------

WORLDBANK_TO_MVM: dict[str, tuple[str, Callable | None]] = {
    # --- Identity ---
    "id":                                   ("id",                   lambda v: f"WB:{v}"),
    "code":                                 ("id",                   lambda v: f"WB:{v}"),

    # --- Title ---
    "name":                                 ("title",               _strip),

    # --- Description ---
    "description":                          ("description",         _strip),
    "lastupdated":                          ("last_updated",        _iso_date),

    # --- Publisher ---
    "_publisher":                           ("publisher",           lambda _: "World Bank"),
    "_publisher_type":                      ("publisher_type",      lambda _: "IO"),

    # --- Keywords (from topics endpoint, joined at crawl time) ---
    "_topics":                              ("keywords",            None),

    # --- Geographic coverage ---
    "_countries":                           ("geographic_coverage", None),

    # --- Access ---
    "_access_type":                         ("access_type",         lambda _: "open"),
    "_license":                             ("license",             lambda _: "CC-BY 4.0"),

    # --- Formats ---
    "_formats":                             ("formats",             lambda _: ["JSON", "XML", "CSV"]),

    # --- URL ---
    "url":                                  ("dataset_url",         _strip),
    "_dataset_url":                         ("dataset_url",         _strip),
    "_source_portal":                       ("source_portal",       _strip),

    # --- Language ---
    "_languages":                           ("languages",           lambda _: ["en"]),

    # --- Metadata standard ---
    "_schema_detected":                     ("metadata_standard",   lambda _: "DCAT"),
}


# ---------------------------------------------------------------------------
# 6. SCHEMA DETECTION
# Called first by harmoniser.py to select the right mapping table.
# Returns one of: "SDMX" | "DCAT" | "DublinCore" | "DDI" | "WorldBank" | "unknown"
# ---------------------------------------------------------------------------

SCHEMA_DETECTION_SIGNALS: dict[str, list[str]] = {
    "PxWeb": [
        "pxweb_path",
        "variables",
    ],
    "SDMX": [
        "data.dataflows",
        "data.structures",
        "sdmx",
        "urn:sdmx",
        "agencyID",
        "FREQ",
        "REF_AREA",
    ],
    "DCAT": [
        "dcat:",
        "dct:title",
        "dcat:Dataset",
        "@type",
        "dcat:keyword",
        "dcat:distribution",
    ],
    "DublinCore": [
        "dc:title",
        "dc:identifier",
        "dcterms:",
        "xmlns:dc=",
    ],
    "DDI": [
        "stdyDscr",
        "dataDscr",
        "codeBook",
        "xmlns:ddi",
    ],
    "WorldBank": [
        "lastupdated",
        "sourceNote",
        "sourceOrganization",
        "api.worldbank.org",
    ],
}

# ---------------------------------------------------------------------------
# 6b. PXWEB → MVM
# Statistics Finland uses the PxWeb REST API, which returns a flat JSON
# response with a top-level "title" field and a "variables" array.
# Portal-level defaults supply publisher, access, license, formats.
# ---------------------------------------------------------------------------

PXWEB_TO_MVM: dict[str, tuple[str, Callable | None]] = {
    # --- Title ---
    "title":              ("title",            _strip),

    # --- Injected by crawler / portal defaults ---
    "_source_portal":     ("source_portal",    _strip),
    "_publisher_type":    ("publisher_type",   _strip),
    "_formats":           ("formats",          None),
    "_access_type":       ("access_type",      None),
    "_license":           ("license",          _strip),
    "_dataset_url":       ("dataset_url",      _strip),
}


SCHEMA_TO_MAPPING: dict[str, dict] = {
    "PxWeb":       PXWEB_TO_MVM,
    "SDMX":        SDMX_TO_MVM,
    "DCAT":        DCAT_TO_MVM,
    "DublinCore":  DUBLIN_CORE_TO_MVM,
    "DDI":         DDI_TO_MVM,
    "WorldBank":   WORLDBANK_TO_MVM,
}

# Fields that are almost always missing from deterministic mapping
# and should be sent directly to LLM without attempting extraction.
LLM_ONLY_FIELDS: set[str] = {
    "themes",           # requires COFOG/SDMX classification knowledge
    "provenance",       # often buried in long prose
    "access_conditions", # varies wildly in format
    "confidence_score", # assigned by LLM only
}

# Fields where null is acceptable (no LLM fallback needed if missing).
NULLABLE_FIELDS: set[str] = {
    "temporal_coverage_end",
    "contact_point",
    "provenance",
    "license",
    "themes",
}


# ---------------------------------------------------------------------------
# 7. PORTAL-LEVEL DEFAULTS
# Values injected by the crawler before harmonisation, not derivable
# from the metadata record itself.
# ---------------------------------------------------------------------------

PORTAL_DEFAULTS: dict[str, dict[str, Any]] = {
    "statistics_finland": {
        "_source_portal":   "statfin",
        "_publisher":       "Statistics Finland",
        "_publisher_type":  "NSO",
        "_languages":       ["fi", "sv", "en"],
        "_formats":         ["JSON", "SDMX", "PX", "CSV"],
        "_access_type":     "open",
        "_license":         "CC-BY 4.0",
        "_schema_detected": "PxWeb",
    },
    "eurostat": {
        "_source_portal":   "eurostat",
        "_publisher":       "Eurostat",
        "_publisher_type":  "IO",
        "_languages":       ["en", "fr", "de"],
        "_formats":         ["SDMX", "TSV", "XLSX", "JSON"],
        "_access_type":     "open",
        "_license":         "CC-BY 4.0",
        "_schema_detected": "SDMX",
    },
    "world_bank": {
        "_source_portal":   "worldbank",
        "_publisher":       "World Bank",
        "_publisher_type":  "IO",
        "_languages":       ["en"],
        "_formats":         ["JSON", "XML", "CSV"],
        "_access_type":     "open",
        "_license":         "CC-BY 4.0",
        "_schema_detected": "WorldBank",
    },
    "oecd": {
        "_source_portal":   "oecd",
        "_publisher":       "OECD",
        "_publisher_type":  "IO",
        "_languages":       ["en", "fr"],
        "_formats":         ["SDMX", "CSV", "JSON"],
        "_access_type":     "open",
        "_license":         "CC-BY 4.0",
        "_schema_detected": "SDMX",
    },
    "un_data": {
        "_source_portal":   "undata",
        "_publisher":       "United Nations Statistics Division",
        "_publisher_type":  "IO",
        "_languages":       ["en"],
        "_formats":         ["SDMX", "CSV"],
        "_access_type":     "open",
        "_license":         "CC-BY 4.0",
        "_schema_detected": "SDMX",
    },
}


# ---------------------------------------------------------------------------
# 8. MVM FIELD COVERAGE REPORT
# Tracks which MVM fields are covered deterministically per schema.
# Used at startup to log expected LLM fallback rate.
# ---------------------------------------------------------------------------

ALL_MVM_FIELDS: set[str] = {
    "id", "title", "description", "publisher", "publisher_type",
    "source_portal", "dataset_url", "keywords", "themes",
    "geographic_coverage", "temporal_coverage_start", "temporal_coverage_end",
    "update_frequency", "last_updated", "access_type", "access_conditions",
    "license", "formats", "languages", "provenance", "contact_point",
    "metadata_standard", "ingestion_timestamp", "confidence_score",
}

def coverage_report() -> dict[str, dict[str, Any]]:
    """
    Returns a dict showing deterministic field coverage per schema.
    Run at startup; log to Application Insights.
    """
    report = {}
    for schema_name, mapping in SCHEMA_TO_MAPPING.items():
        covered = {mvm_field for _, (mvm_field, _) in mapping.items()
                   if not mvm_field.startswith("_")}
        missing = ALL_MVM_FIELDS - covered - {"ingestion_timestamp", "confidence_score"}
        report[schema_name] = {
            "covered_count":    len(covered),
            "total_fields":     len(ALL_MVM_FIELDS),
            "coverage_pct":     round(len(covered) / len(ALL_MVM_FIELDS) * 100, 1),
            "covered_fields":   sorted(covered),
            "llm_fallback_fields": sorted(missing),
        }
    return report


if __name__ == "__main__":
    import json
    print(json.dumps(coverage_report(), indent=2))
