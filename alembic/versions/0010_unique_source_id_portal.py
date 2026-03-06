"""Add unique constraint on (source_id, portal_id) and deduplicate

Revision ID: 0010_unique_source_id_portal
Revises: 0009_backfill_description
Create Date: 2026-03-06
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0010_unique_source_id_portal"
down_revision = "0009_backfill_description"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Deduplicate: for each (source_id, portal_id) keep the most recently
    # updated record (highest ingestion_timestamp), delete the rest.
    op.execute(text("""
        DELETE FROM datasets
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY source_id, portal_id
                           ORDER BY ingestion_timestamp DESC NULLS LAST
                       ) AS rn
                FROM datasets
            ) ranked
            WHERE rn > 1
        )
    """))

    # Add unique constraint
    op.create_unique_constraint(
        "uq_datasets_source_id_portal_id",
        "datasets",
        ["source_id", "portal_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_datasets_source_id_portal_id", "datasets", type_="unique")
