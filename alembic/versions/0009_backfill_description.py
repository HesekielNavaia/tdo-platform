"""Backfill description = title where description is null or empty

Revision ID: 0009_backfill_description
Revises: 0008_merge_branches
Create Date: 2026-03-06
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0009_backfill_description"
down_revision = "0008_merge_branches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("""
        UPDATE datasets
        SET description = title
        WHERE (description IS NULL OR description = '')
          AND title IS NOT NULL AND title <> ''
    """))


def downgrade() -> None:
    pass
