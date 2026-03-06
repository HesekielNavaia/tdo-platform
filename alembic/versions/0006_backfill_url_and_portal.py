"""Backfill dataset_url and normalize portal_id to short names

Revision ID: 0006_backfill_url_and_portal
Revises: 0005_add_embedding_vector
Create Date: 2026-03-05
"""
from __future__ import annotations

from alembic import op

revision = "0006_backfill_url_and_portal"
down_revision = "0005_add_embedding_vector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------
    # 1. Normalize portal_id and source_portal to short names.
    #    Old values were full URLs (e.g. "https://ec.europa.eu/eurostat").
    # -------------------------------------------------------------------
    op.execute("""
        UPDATE datasets
        SET portal_id = 'eurostat', source_portal = 'eurostat'
        WHERE (portal_id LIKE '%eurostat%' OR source_portal LIKE '%eurostat%')
          AND portal_id != 'eurostat';
    """)
    op.execute("""
        UPDATE datasets
        SET portal_id = 'oecd', source_portal = 'oecd'
        WHERE (portal_id LIKE '%oecd%' OR source_portal LIKE '%oecd%')
          AND portal_id != 'oecd';
    """)
    op.execute("""
        UPDATE datasets
        SET portal_id = 'worldbank', source_portal = 'worldbank'
        WHERE (portal_id LIKE '%worldbank%' OR portal_id LIKE '%world%bank%'
               OR source_portal LIKE '%worldbank%')
          AND portal_id != 'worldbank';
    """)
    op.execute("""
        UPDATE datasets
        SET portal_id = 'statfin', source_portal = 'statfin'
        WHERE (portal_id LIKE '%stat.fi%' OR source_portal LIKE '%stat.fi%')
          AND portal_id != 'statfin';
    """)
    op.execute("""
        UPDATE datasets
        SET portal_id = 'undata', source_portal = 'undata'
        WHERE (portal_id LIKE '%un.org%' OR source_portal LIKE '%un.org%')
          AND portal_id != 'undata';
    """)

    # Also normalize portal_id in dataset_aliases so future harvests
    # correctly find existing records instead of creating duplicates.
    op.execute("""
        UPDATE dataset_aliases SET portal_id = 'eurostat'
        WHERE portal_id LIKE '%eurostat%' AND portal_id != 'eurostat';
    """)
    op.execute("""
        UPDATE dataset_aliases SET portal_id = 'oecd'
        WHERE portal_id LIKE '%oecd%' AND portal_id != 'oecd';
    """)
    op.execute("""
        UPDATE dataset_aliases SET portal_id = 'worldbank'
        WHERE (portal_id LIKE '%worldbank%' OR portal_id LIKE '%world%bank%')
          AND portal_id != 'worldbank';
    """)
    op.execute("""
        UPDATE dataset_aliases SET portal_id = 'statfin'
        WHERE portal_id LIKE '%stat.fi%' AND portal_id != 'statfin';
    """)
    op.execute("""
        UPDATE dataset_aliases SET portal_id = 'undata'
        WHERE portal_id LIKE '%un.org%' AND portal_id != 'undata';
    """)

    # -------------------------------------------------------------------
    # 2. Backfill dataset_url for records where it is missing.
    # -------------------------------------------------------------------

    # Eurostat: https://ec.europa.eu/eurostat/databrowser/view/{source_id}
    op.execute("""
        UPDATE datasets
        SET dataset_url = 'https://ec.europa.eu/eurostat/databrowser/view/' || source_id
        WHERE portal_id = 'eurostat'
          AND (dataset_url IS NULL OR dataset_url = '');
    """)

    # OECD: compound source_ids like "DSD_REG_ECO@DF_GDP" → use part after "@"
    op.execute("""
        UPDATE datasets
        SET dataset_url =
            CASE
                WHEN source_id LIKE '%@%' THEN
                    'https://data-explorer.oecd.org/vis?df[ds]=dsDisseminateFinalDMZ&df[id]='
                    || split_part(source_id, '@', 2)
                    || '&df[ag]=OECD'
                ELSE
                    'https://data-explorer.oecd.org/vis?df[ds]=dsDisseminateFinalDMZ&df[id]='
                    || source_id
                    || '&df[ag]=OECD'
            END
        WHERE portal_id = 'oecd'
          AND (dataset_url IS NULL OR dataset_url = '');
    """)

    # StatFin: source_id = "StatFin/matk/statfin_matk_pxt_117s.px"
    # → https://pxdata.stat.fi/PxWeb/pxweb/en/StatFin/matk/statfin_matk_pxt_117s.px
    op.execute("""
        UPDATE datasets
        SET dataset_url = 'https://pxdata.stat.fi/PxWeb/pxweb/en/' || source_id
        WHERE portal_id = 'statfin'
          AND (dataset_url IS NULL OR dataset_url = '');
    """)

    # World Bank: source_id is the numeric source ID
    op.execute("""
        UPDATE datasets
        SET dataset_url = 'https://data.worldbank.org/source/' || source_id
        WHERE portal_id = 'worldbank'
          AND (dataset_url IS NULL OR dataset_url = '');
    """)

    # UN Data: source_id is SDMX dataflow ID e.g. "DF_UNDATA_COUNTRYDATA"
    op.execute("""
        UPDATE datasets
        SET dataset_url = 'https://data.un.org/SdmxBrowser/start?df[id]=' || source_id || '&df[ag]=UNSD'
        WHERE portal_id = 'undata'
          AND (dataset_url IS NULL OR dataset_url = '');
    """)


def downgrade() -> None:
    # Downgrade is intentionally a no-op — we don't want to re-corrupt data.
    pass
