"""Fix WorldBank dataset_url: data.worldbank.org/source -> databank.worldbank.org/source

Revision ID: 0011_fix_worldbank_url
Revises: 0010_unique_source_id_portal
Create Date: 2026-03-06
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0011_fix_worldbank_url"
down_revision = "0010_unique_source_id_portal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("""
        UPDATE datasets
        SET dataset_url = REPLACE(dataset_url,
            'https://data.worldbank.org/source/',
            'https://databank.worldbank.org/source/')
        WHERE portal_id = 'worldbank'
          AND dataset_url LIKE 'https://data.worldbank.org/source/%'
    """))


def downgrade() -> None:
    op.execute(text("""
        UPDATE datasets
        SET dataset_url = REPLACE(dataset_url,
            'https://databank.worldbank.org/source/',
            'https://data.worldbank.org/source/')
        WHERE portal_id = 'worldbank'
          AND dataset_url LIKE 'https://databank.worldbank.org/source/%'
    """))
