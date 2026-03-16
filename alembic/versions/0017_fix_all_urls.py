"""Fix all outstanding dataset URL issues across all portals

1. StatFin: PXWeb → PxWeb (correct mixed case for the PxWeb viewer)
2. UN Data SDG series: old ?indicator= format → dataportal/database/DataSeries/{code}
3. UN Data SDMX non-SDG: fix broken/missing URLs → SdmxBrowser format
4. WorldBank source records (numeric source_id): add databank.worldbank.org/source/{id}

Revision ID: 0017_fix_all_urls
Revises: 0016_fix_undata_urls
Create Date: 2026-03-16
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0017_fix_all_urls"
down_revision = "0016_fix_undata_urls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. StatFin: PXWeb → PxWeb (viewer URL case fix)
    op.execute(text("""
        UPDATE datasets
        SET dataset_url = REPLACE(dataset_url, '/PXWeb/', '/PxWeb/')
        WHERE portal_id = 'statfin'
          AND dataset_url LIKE '%/PXWeb/%'
    """))

    # 2. UN Data SDG series: old ?indicator= format → dataportal DataSeries URL
    #    source_id format: 'SDG_EN_ATM_GHGT_WLU' → series code = 'EN_ATM_GHGT_WLU'
    op.execute(text("""
        UPDATE datasets
        SET dataset_url =
            'https://unstats.un.org/sdgs/dataportal/database/DataSeries/'
            || REGEXP_REPLACE(source_id, '^SDG_', '')
        WHERE portal_id = 'undata'
          AND source_id LIKE 'SDG_%'
          AND (dataset_url LIKE '%indicators/database/?indicator=%'
               OR dataset_url NOT LIKE '%dataportal/database/DataSeries/%')
    """))

    # 3. UN Data SDMX non-SDG: fix any records with wrong/missing URLs
    #    These have source_ids like 'DF_SEEA_AEA', 'NASEC_IDCFINA_A', etc.
    op.execute(text("""
        UPDATE datasets
        SET dataset_url =
            'https://data.un.org/SdmxBrowser/start?df[id]=' || source_id || '&df[ag]=UNSD'
        WHERE portal_id = 'undata'
          AND source_id NOT LIKE 'SDG_%'
          AND (dataset_url IS NULL
               OR dataset_url = 'https://unstats.un.org/sdgs/'
               OR dataset_url LIKE '%/sdgs/indicators/database/%'
               OR dataset_url LIKE '%Data.aspx%')
    """))

    # 4. WorldBank source records (numeric source_id): add databank.worldbank.org URL
    op.execute(text("""
        UPDATE datasets
        SET dataset_url = 'https://databank.worldbank.org/source/' || source_id
        WHERE portal_id = 'worldbank'
          AND source_id ~ '^[0-9]+$'
          AND (dataset_url IS NULL OR dataset_url = '')
    """))


def downgrade() -> None:
    pass
