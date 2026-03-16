"""Fix Eurostat URLs with duplicate /default/table suffix

Some migration runs resulted in URLs like:
  .../databrowser/view/RAIL_GO_TOTAL/default/table/default/table

This migration strips the duplicate suffix.

Revision ID: 0018_fix_eurostat_double_suffix
Revises: 0017_fix_all_urls
Create Date: 2026-03-16
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0018_fix_eurostat_double_suffix"
down_revision = "0017_fix_all_urls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove any duplicate /default/table suffix appended multiple times
    # Keep removing until no more duplicates exist (loop via multiple executes)
    for _ in range(5):
        op.execute(text("""
            UPDATE datasets
            SET dataset_url = REPLACE(
                dataset_url,
                '/default/table/default/table',
                '/default/table'
            )
            WHERE portal_id = 'eurostat'
              AND dataset_url LIKE '%/default/table/default/table%'
        """))

    # Also ensure all eurostat URLs end with exactly /default/table (no ?lang=en)
    op.execute(text("""
        UPDATE datasets
        SET dataset_url = REPLACE(dataset_url, '/default/table?lang=en', '/default/table')
        WHERE portal_id = 'eurostat'
          AND dataset_url LIKE '%/default/table?lang=en%'
    """))


def downgrade() -> None:
    pass
