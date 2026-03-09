"""Fix dataset_url formats: StatFin PxWeb case, Eurostat view format, UN Data Data.aspx

- StatFin: PXWeb → PxWeb (case fix in viewer URL)
- Eurostat: normalize to /databrowser/view/{id}/default/table (drop extractionId and ?lang=en variants)
- UN Data UNSD: SdmxBrowser/start → Data.aspx?d=UNSD&f=series%3A{id}

Revision ID: 0015_fix_dataset_url_formats
Revises: 0014_backfill_embedding_vec
Create Date: 2026-03-09
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0015_fix_dataset_url_formats"
down_revision = "0014_backfill_embedding_vec"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. StatFin: PXWeb → PxWeb (correct mixed case for the PxWeb viewer)
    op.execute(text("""
        UPDATE datasets
        SET dataset_url = REPLACE(dataset_url, '/PXWeb/', '/PxWeb/')
        WHERE portal_id = 'statfin'
          AND dataset_url LIKE '%/PXWeb/%'
    """))

    # 2a. Eurostat: extractionId format → canonical view format
    op.execute(text("""
        UPDATE datasets
        SET dataset_url =
            'https://ec.europa.eu/eurostat/databrowser/view/' || source_id || '/default/table'
        WHERE portal_id = 'eurostat'
          AND dataset_url LIKE '%extractionId=%'
    """))

    # 2b. Eurostat: strip ?lang=en suffix from view URLs
    op.execute(text("""
        UPDATE datasets
        SET dataset_url = REPLACE(dataset_url, '/default/table?lang=en', '/default/table')
        WHERE portal_id = 'eurostat'
          AND dataset_url LIKE '%/default/table?lang=en'
    """))

    # 2c. Eurostat: add /default/table to bare view URLs
    op.execute(text("""
        UPDATE datasets
        SET dataset_url = dataset_url || '/default/table'
        WHERE portal_id = 'eurostat'
          AND dataset_url LIKE 'https://ec.europa.eu/eurostat/databrowser/view/%'
          AND dataset_url NOT LIKE '%/default/table'
    """))

    # 3. UN Data: SdmxBrowser → Data.aspx format
    op.execute(text("""
        UPDATE datasets
        SET dataset_url =
            'https://data.un.org/Data.aspx?d=UNSD&f=series%3A' || source_id
        WHERE portal_id = 'un_data'
          AND dataset_url LIKE '%SdmxBrowser%'
    """))


def downgrade() -> None:
    pass
