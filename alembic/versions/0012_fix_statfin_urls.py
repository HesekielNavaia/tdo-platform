"""Fix StatFin dataset_url: old /PxWeb/.../StatFin/{folder}/ → /PXWeb/.../StatFin/StatFin__{folder}/

The PxWeb viewer URLs without the double-underscore path format return HTTP 500.
Rebuild all StatFin URLs from source_id using the correct format.

Revision ID: 0012_fix_statfin_urls
Revises: 0011_fix_worldbank_url
Create Date: 2026-03-06
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0012_fix_statfin_urls"
down_revision = "0011_fix_worldbank_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rebuild dataset_url from source_id for all StatFin records.
    # source_id format: "StatFin/{folder}/{table}.px"
    # Correct viewer URL:  "https://pxdata.stat.fi/PXWeb/pxweb/en/StatFin/StatFin__{folder}/{table}.px"
    op.execute(text("""
        UPDATE datasets
        SET dataset_url =
            'https://pxdata.stat.fi/PXWeb/pxweb/en/StatFin/StatFin__'
            || SPLIT_PART(REGEXP_REPLACE(source_id, '^StatFin/', ''), '/', 1)
            || '/'
            || SPLIT_PART(REGEXP_REPLACE(source_id, '^StatFin/', ''), '/', 2)
        WHERE portal_id = 'statfin'
          AND source_id LIKE 'StatFin/%/%'
    """))


def downgrade() -> None:
    # Restore old (broken) format
    op.execute(text("""
        UPDATE datasets
        SET dataset_url =
            'https://pxdata.stat.fi/PxWeb/pxweb/en/StatFin/'
            || SPLIT_PART(REGEXP_REPLACE(source_id, '^StatFin/', ''), '/', 1)
            || '/'
            || SPLIT_PART(REGEXP_REPLACE(source_id, '^StatFin/', ''), '/', 2)
        WHERE portal_id = 'statfin'
          AND source_id LIKE 'StatFin/%/%'
    """))
