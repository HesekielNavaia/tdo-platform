"""Stub: StatFin/Eurostat/OECD URL fixes (superseded by 0013)

This file is kept as a stub so Alembic can locate the revision if it was
already applied to the database. All functional SQL is in 0013.

Revision ID: 0012_fix_statfin_eurostat_oecd_urls
Revises: 0011_fix_worldbank_url
Create Date: 2026-03-06
"""
from __future__ import annotations

from alembic import op

revision = "0012_fix_statfin_eurostat_oecd_urls"
down_revision = "0011_fix_worldbank_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No-op stub — functional changes moved to 0013_fix_eurostat_oecd_worldbank_urls
    pass


def downgrade() -> None:
    pass
