"""Backfill dataset_url for UN Data records

Revision ID: 0007_backfill_undata_url
Revises: 0006_backfill_url_and_portal
Create Date: 2026-03-06
"""
from __future__ import annotations

from alembic import op

revision = "0007_backfill_undata_url"
down_revision = "0006_backfill_url_and_portal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # UN Data: source_id is SDMX dataflow ID e.g. "DF_UNDATA_COUNTRYDATA"
    op.execute("""
        UPDATE datasets
        SET dataset_url = 'https://data.un.org/SdmxBrowser/start?df[id]=' || source_id || '&df[ag]=UNSD'
        WHERE portal_id = 'undata'
          AND (dataset_url IS NULL OR dataset_url = '');
    """)


def downgrade() -> None:
    pass
