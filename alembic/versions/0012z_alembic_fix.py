"""Widen alembic_version varchar and apply pending URL fixes

The alembic_version.version_num column is varchar(32), which is too short for
revision IDs like '0012_fix_statfin_eurostat_oecd_urls' (36 chars). This migration:
  1. Widens the column to varchar(128)
  2. Runs all URL fix SQL from 0015 and 0016 (which may not have applied)
  3. The subsequent stub migrations (0012_fix_statfin_eurostat_oecd_urls → 0013 → 0014)
     can now be recorded without hitting the varchar limit.

Revision ID: 0012z_alembic_fix
Revises: 0012_fix_statfin_urls
Create Date: 2026-03-10
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0012z_alembic_fix"
down_revision = "0012_fix_statfin_urls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Widen version_num to accommodate long revision IDs
    op.execute(text(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE varchar(128)"
    ))

    # 2. StatFin: PXWeb → PxWeb (from 0015, may already be applied)
    op.execute(text("""
        UPDATE datasets
        SET dataset_url = REPLACE(dataset_url, '/PXWeb/', '/PxWeb/')
        WHERE portal_id = 'statfin'
          AND dataset_url LIKE '%/PXWeb/%'
    """))

    # 3a. Eurostat: extractionId format → canonical view format (from 0015)
    op.execute(text("""
        UPDATE datasets
        SET dataset_url =
            'https://ec.europa.eu/eurostat/databrowser/view/' || source_id || '/default/table'
        WHERE portal_id = 'eurostat'
          AND dataset_url LIKE '%extractionId=%'
    """))

    # 3b. Eurostat: strip ?lang=en suffix
    op.execute(text("""
        UPDATE datasets
        SET dataset_url = REPLACE(dataset_url, '/default/table?lang=en', '/default/table')
        WHERE portal_id = 'eurostat'
          AND dataset_url LIKE '%/default/table?lang=en'
    """))

    # 3c. Eurostat: add /default/table to bare view URLs
    op.execute(text("""
        UPDATE datasets
        SET dataset_url = dataset_url || '/default/table'
        WHERE portal_id = 'eurostat'
          AND dataset_url LIKE 'https://ec.europa.eu/eurostat/databrowser/view/%'
          AND dataset_url NOT LIKE '%/default/table'
    """))

    # 4. UN Data SdmxBrowser fix (from 0015)
    op.execute(text("""
        UPDATE datasets
        SET dataset_url =
            'https://data.un.org/SdmxBrowser/start?df[id]=' || source_id || '&df[ag]=UNSD'
        WHERE portal_id = 'undata'
          AND source_id NOT LIKE 'SDG_%'
          AND (dataset_url LIKE '%Data.aspx%' OR dataset_url IS NULL)
    """))

    # 5. UN Data SDG series: series code → dataportal (from 0016)
    op.execute(text("""
        UPDATE datasets
        SET dataset_url =
            'https://unstats.un.org/sdgs/dataportal/database/DataSeries/'
            || REGEXP_REPLACE(source_id, '^SDG_', '')
        WHERE portal_id = 'undata'
          AND source_id LIKE 'SDG_%'
    """))


def downgrade() -> None:
    pass
