"""Backfill embedding_vec from JSONB embedding for all records missing it

Records inserted after migration 0005 have the JSONB embedding column populated
but embedding_vec (pgvector) NULL, so semantic search skips them. This migration
re-runs the same backfill so all existing records become searchable.

Revision ID: 0014_backfill_embedding_vec
Revises: 0013_fix_eurostat_oecd_worldbank_urls, 0013_fix_eurostat_urls
Create Date: 2026-03-08
"""
from __future__ import annotations

from alembic import op


revision = "0014_backfill_embedding_vec"
down_revision = ("0013_fix_eurostat_oecd_worldbank_urls", "0013_fix_eurostat_urls")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE datasets
        SET embedding_vec = embedding::text::vector
        WHERE embedding IS NOT NULL
          AND jsonb_array_length(embedding) = 1024
          AND embedding_vec IS NULL
    """)


def downgrade() -> None:
    pass
