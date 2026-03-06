"""Fix source_portal for old StatFin records from URL to portal_id

Revision ID: 0006_fix_statfin_portal_key
Revises: 0005_add_embedding_vector
Create Date: 2026-03-06
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0006_fix_statfin_portal_key"
down_revision = "0005_add_embedding_vector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text(
        "UPDATE datasets SET source_portal = 'statfin' WHERE source_portal = 'https://stat.fi'"
    ))


def downgrade() -> None:
    op.execute(text(
        "UPDATE datasets SET source_portal = 'https://stat.fi' WHERE source_portal = 'statfin'"
    ))
