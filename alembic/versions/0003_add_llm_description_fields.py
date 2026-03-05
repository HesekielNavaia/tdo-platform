"""Add LLM-extracted description fields to datasets table

Revision ID: 0003_add_llm_description_fields
Revises: 0002_create_aad_users
Create Date: 2026-03-05
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_add_llm_description_fields"
down_revision = "0002_create_aad_users"
branch_labels = None
depends_on = None

NEW_TEXT_COLUMNS = [
    "time_series_length",
    "methodology_url",
    "unit_of_measure",
]
NEW_ARRAY_COLUMNS = [
    "related_datasets",
    "subject_classification",
]
NEW_FLOAT_COLUMNS = [
    "time_series_length_confidence",
    "methodology_url_confidence",
    "related_datasets_confidence",
    "subject_classification_confidence",
    "unit_of_measure_confidence",
    "observation_count_estimate_confidence",
]


def upgrade() -> None:
    for col in NEW_TEXT_COLUMNS:
        op.add_column("datasets", sa.Column(col, sa.Text(), nullable=True))
    for col in NEW_ARRAY_COLUMNS:
        op.add_column("datasets", sa.Column(col, sa.ARRAY(sa.Text()), nullable=True))
    op.add_column(
        "datasets",
        sa.Column("observation_count_estimate", sa.Integer(), nullable=True),
    )
    for col in NEW_FLOAT_COLUMNS:
        op.add_column("datasets", sa.Column(col, sa.Float(), nullable=True))


def downgrade() -> None:
    all_cols = (
        NEW_TEXT_COLUMNS
        + NEW_ARRAY_COLUMNS
        + ["observation_count_estimate"]
        + NEW_FLOAT_COLUMNS
    )
    for col in reversed(all_cols):
        op.drop_column("datasets", col)
