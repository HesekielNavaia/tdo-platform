"""Fix Eurostat table URL suffix, OECD DF_ prefix, World Bank portal_id

Revision ID: 0013_fix_eurostat_oecd_worldbank_urls
Revises: 0012_fix_statfin_urls
Create Date: 2026-03-06
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0013_fix_eurostat_oecd_worldbank_urls"
down_revision = ("0012_fix_statfin_urls", "0012_fix_statfin_eurostat_oecd_urls")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # 1. Eurostat: add /default/table?lang=en suffix to all dataset URLs.
    #    Current: .../databrowser/view/{id}
    #    Correct: .../databrowser/view/{id}/default/table?lang=en
    # -----------------------------------------------------------------------
    op.execute(text("""
        UPDATE datasets
        SET dataset_url = dataset_url || '/default/table?lang=en'
        WHERE portal_id = 'eurostat'
          AND dataset_url LIKE 'https://ec.europa.eu/eurostat/databrowser/view/%'
          AND dataset_url NOT LIKE '%/default/table?lang=en'
    """))

    # -----------------------------------------------------------------------
    # 2. OECD: ensure dataset URLs include DF_ prefix in df[id] parameter.
    #    If stored source_ids are short form (e.g. AGBIO), add DF_ prefix.
    # -----------------------------------------------------------------------
    op.execute(text("""
        UPDATE datasets
        SET dataset_url =
            'https://data-explorer.oecd.org/vis?df[ds]=dsDisseminateFinalDMZ&df[id]=DF_'
            || source_id || '&df[ag]=OECD'
        WHERE portal_id = 'oecd'
          AND dataset_url IS NOT NULL
          AND dataset_url NOT LIKE '%df[id]=DF_%'
    """))

    # -----------------------------------------------------------------------
    # 3. World Bank: ensure portal_id is 'worldbank' (no underscore).
    # -----------------------------------------------------------------------
    op.execute(text("""
        UPDATE datasets
        SET portal_id = 'worldbank', source_portal = 'worldbank'
        WHERE portal_id = 'world_bank'
    """))
    op.execute(text("""
        UPDATE dataset_aliases
        SET portal_id = 'worldbank'
        WHERE portal_id = 'world_bank'
    """))


def downgrade() -> None:
    pass
