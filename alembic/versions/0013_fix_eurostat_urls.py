"""Fix Eurostat dataset_url: /databrowser/view/{id} → /databrowser/explore/all/all_themes?extractionId={id}

The old /databrowser/view/{id} URL lands on a generic explore page.
The correct direct-dataset URL uses the extractionId query parameter.

Revision ID: 0013_fix_eurostat_urls
Revises: 0012_fix_statfin_urls
Create Date: 2026-03-06
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0013_fix_eurostat_urls"
down_revision = "0012_fix_statfin_urls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("""
        UPDATE datasets
        SET dataset_url =
            'https://ec.europa.eu/eurostat/databrowser/explore/all/all_themes?lang=en&display=list&sort=category&extractionId='
            || source_id
        WHERE portal_id = 'eurostat'
    """))


def downgrade() -> None:
    op.execute(text("""
        UPDATE datasets
        SET dataset_url =
            'https://ec.europa.eu/eurostat/databrowser/view/' || source_id || '/default/table?lang=en'
        WHERE portal_id = 'eurostat'
    """))
