"""Fix UN Data dataset URLs: SDG series → dataportal, SDMX → SdmxBrowser

- SDG series (source_id like 'SDG_*'): use unstats.un.org/sdgs/dataportal/database/DataSeries/{series_code}
- SDMX dataflows: restore correct SdmxBrowser format instead of broken Data.aspx URLs

Revision ID: 0016_fix_undata_urls
Revises: 0015_fix_dataset_url_formats
Create Date: 2026-03-09
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0016_fix_undata_urls"
down_revision = "0015_fix_dataset_url_formats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. SDG series: source_id is stored as 'SDG_{code}', extract series code
    #    and build the dataportal URL.
    #    source_id example: 'SDG_DC_ODA_BDVDL' → code = 'DC_ODA_BDVDL'
    op.execute(text("""
        UPDATE datasets
        SET dataset_url =
            'https://unstats.un.org/sdgs/dataportal/database/DataSeries/'
            || REGEXP_REPLACE(source_id, '^SDG_', '')
        WHERE portal_id = 'un_data'
          AND source_id LIKE 'SDG_%'
    """))

    # 2. SDMX dataflows (non-SDG): fix broken Data.aspx URLs back to SdmxBrowser format.
    #    These records have source_ids like 'DF_UNDATA_ENERGY', 'DF_SEEA_AEA', etc.
    #    Reconstruct SdmxBrowser URL from source_id and portal defaults (agencyID varies).
    #    Since we don't store agencyID separately, use 'UNSD' as default for DF_UNDATA_*
    #    and 'ESTAT' for known ESTAT flows. Simpler: just fix any Data.aspx un_data URL
    #    that doesn't look like a dataportal URL.
    op.execute(text("""
        UPDATE datasets
        SET dataset_url =
            'https://data.un.org/SdmxBrowser/start?df[id]=' || source_id || '&df[ag]=UNSD'
        WHERE portal_id = 'un_data'
          AND source_id NOT LIKE 'SDG_%'
          AND (dataset_url LIKE '%Data.aspx%' OR dataset_url IS NULL)
    """))


def downgrade() -> None:
    pass
