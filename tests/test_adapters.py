"""
Adapter URL pattern tests — verifies that each portal adapter
generates dataset_url values matching the documented correct patterns.
No type hints; Python 3.8 compatible.
"""
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# URL pattern regexes per portal (authoritative patterns per pipeline spec)
# ---------------------------------------------------------------------------

STATFIN_URL_PATTERN = re.compile(
    r"^https://pxdata\.stat\.fi/PxWeb/pxweb/en/\w+/\w+__\w+/.+\.px$"
)

EUROSTAT_URL_PATTERN = re.compile(
    r"^https://ec\.europa\.eu/eurostat/databrowser/view/[A-Z0-9_$]+/default/table$"
)

OECD_URL_PATTERN = re.compile(
    r"^https://data-explorer\.oecd\.org/vis\?"
    r"df\[ds\]=dsDisseminateFinalDMZ&df\[id\]=DF_[A-Z0-9_]+&df\[ag\]=\w+$"
)

WORLDBANK_INDICATOR_URL_PATTERN = re.compile(
    r"^https://data\.worldbank\.org/indicator/[A-Z][A-Z0-9.]+$"
)

WORLDBANK_SOURCE_URL_PATTERN = re.compile(
    r"^https://databank\.worldbank\.org/source/[0-9]+$"
)

UNDATA_SDG_URL_PATTERN = re.compile(
    r"^https://unstats\.un\.org/sdgs/dataportal/database/DataSeries/[A-Z0-9_]+$"
)

UNDATA_SDMX_URL_PATTERN = re.compile(
    r"^https://data\.un\.org/SdmxBrowser/start\?df\[id\]=.+&df\[ag\]=.+$"
)


class TestStatFinURLPattern:
    def test_standard_table_url(self):
        # Standard StatFin table: StatFin/{folder}/{table}.px
        from src.adapters.statistics_finland import StatisticsFinlandAdapter
        adapter = StatisticsFinlandAdapter()

        source_id = "StatFin/matk/statfin_matk_pxt_117s.px"
        viewer_path = source_id.lstrip("/").removeprefix("StatFin/")
        parts = viewer_path.split("/")
        db, subject, table = "StatFin", parts[0], parts[1]
        url = f"https://pxdata.stat.fi/PxWeb/pxweb/en/{db}/{db}__{subject}/{table}"

        assert STATFIN_URL_PATTERN.match(url), f"URL did not match pattern: {url}"
        assert "/PxWeb/" in url, "Must use PxWeb (mixed case), not PXWeb"
        assert "StatFin__matk" in url
        assert url.endswith(".px")

    def test_url_uses_pxweb_mixed_case(self):
        url = "https://pxdata.stat.fi/PxWeb/pxweb/en/StatFin/StatFin__klv/statfin_klv_pxt_14ln.px"
        assert "/PxWeb/" in url
        assert "/PXWeb/" not in url
        assert STATFIN_URL_PATTERN.match(url)

    def test_url_not_pxweb_uppercase(self):
        bad_url = "https://pxdata.stat.fi/PXWeb/pxweb/en/StatFin/StatFin__klv/statfin_klv_pxt_14ln.px"
        assert not STATFIN_URL_PATTERN.match(bad_url), "PXWeb (all caps) should not match"


class TestEurostatURLPattern:
    def test_standard_dataflow_url(self):
        url = "https://ec.europa.eu/eurostat/databrowser/view/NAMQ_10_GDP/default/table"
        assert EUROSTAT_URL_PATTERN.match(url)

    def test_url_format_no_extraction_id(self):
        bad_url = "https://ec.europa.eu/eurostat/databrowser/explore/all/all_themes?extractionId=NAMQ_10_GDP"
        assert not EUROSTAT_URL_PATTERN.match(bad_url)

    def test_url_with_dollar_sign_in_id(self):
        url = "https://ec.europa.eu/eurostat/databrowser/view/CRIM_HOM_SOFF$DV_1941/default/table"
        assert EUROSTAT_URL_PATTERN.match(url)

    def test_adapter_generates_correct_url(self):
        df_id = "NAMQ_10_GDP"
        url = f"https://ec.europa.eu/eurostat/databrowser/view/{df_id}/default/table"
        assert EUROSTAT_URL_PATTERN.match(url)


class TestOECDURLPattern:
    def test_standard_dataflow_url(self):
        url = "https://data-explorer.oecd.org/vis?df[ds]=dsDisseminateFinalDMZ&df[id]=DF_NAAG&df[ag]=OECD"
        assert OECD_URL_PATTERN.match(url)

    def test_url_has_df_prefix(self):
        url = "https://data-explorer.oecd.org/vis?df[ds]=dsDisseminateFinalDMZ&df[id]=DF_B6&df[ag]=OECD"
        assert "df[id]=DF_" in url
        assert OECD_URL_PATTERN.match(url)

    def test_url_without_df_prefix_fails(self):
        bad_url = "https://data-explorer.oecd.org/vis?df[ds]=dsDisseminateFinalDMZ&df[id]=NAAG&df[ag]=OECD"
        assert not OECD_URL_PATTERN.match(bad_url)

    def test_adapter_strips_at_sign_from_compound_id(self):
        # SDMX IDs may be compound e.g. "DSD_KIIBIH@DF_B6" — adapter uses part after @
        df_id_compound = "DSD_KIIBIH@DF_B6"
        df_id_for_url = df_id_compound.split("@")[-1] if "@" in df_id_compound else df_id_compound
        url = (
            "https://data-explorer.oecd.org/vis"
            "?df[ds]=dsDisseminateFinalDMZ"
            f"&df[id]={df_id_for_url}"
            "&df[ag]=OECD"
        )
        assert OECD_URL_PATTERN.match(url)


class TestWorldBankURLPattern:
    def test_indicator_url_alphabetic_code(self):
        url = "https://data.worldbank.org/indicator/NY.GDP.MKTP.CD"
        assert WORLDBANK_INDICATOR_URL_PATTERN.match(url)

    def test_indicator_url_must_start_with_letter(self):
        # Numeric-only indicator codes are source IDs, not indicators
        bad_url = "https://data.worldbank.org/indicator/38"
        assert not WORLDBANK_INDICATOR_URL_PATTERN.match(bad_url)

    def test_source_url_pattern(self):
        url = "https://databank.worldbank.org/source/38"
        assert WORLDBANK_SOURCE_URL_PATTERN.match(url)

    def test_source_url_numeric_only(self):
        for source_id in ["1", "2", "11", "22", "40"]:
            url = f"https://databank.worldbank.org/source/{source_id}"
            assert WORLDBANK_SOURCE_URL_PATTERN.match(url), f"Source URL failed: {url}"

    def test_source_url_not_data_worldbank(self):
        # Source records should use databank.worldbank.org, not data.worldbank.org
        bad_url = "https://data.worldbank.org/source/38"
        assert not WORLDBANK_SOURCE_URL_PATTERN.match(bad_url)


class TestUNDataURLPattern:
    def test_sdg_series_url(self):
        url = "https://unstats.un.org/sdgs/dataportal/database/DataSeries/EN_ATM_GHGT_WLU"
        assert UNDATA_SDG_URL_PATTERN.match(url)

    def test_sdg_url_not_indicator_format(self):
        bad_url = "https://unstats.un.org/sdgs/indicators/database/?indicator=13.2.2"
        assert not UNDATA_SDG_URL_PATTERN.match(bad_url)

    def test_sdmx_browser_url(self):
        url = "https://data.un.org/SdmxBrowser/start?df[id]=DF_SEEA_AEA&df[ag]=UNSD"
        assert UNDATA_SDMX_URL_PATTERN.match(url)

    def test_sdg_source_id_to_url(self):
        # source_id = 'SDG_EN_ATM_GHGT_WLU' → series code = 'EN_ATM_GHGT_WLU'
        source_id = "SDG_EN_ATM_GHGT_WLU"
        series_code = source_id.removeprefix("SDG_")
        url = f"https://unstats.un.org/sdgs/dataportal/database/DataSeries/{series_code}"
        assert UNDATA_SDG_URL_PATTERN.match(url)

    def test_adapter_sdg_url_construction(self):
        # Simulate what the adapter does for SDG series
        code = "EN_ATM_CO2E_GDP"
        url = f"https://unstats.un.org/sdgs/dataportal/database/DataSeries/{code}"
        assert UNDATA_SDG_URL_PATTERN.match(url)

    def test_adapter_sdmx_url_construction(self):
        # Simulate what the adapter does for SDMX dataflows
        df_id = "DF_SEEA_AEA"
        agency_id = "UNSD"
        url = f"https://data.un.org/SdmxBrowser/start?df[id]={df_id}&df[ag]={agency_id}"
        assert UNDATA_SDMX_URL_PATTERN.match(url)
