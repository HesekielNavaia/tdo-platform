"""Merge the two 0006 branches into a single head

Revision ID: 0008_merge_branches
Revises: 0007_backfill_undata_url, 0006_fix_statfin_portal_key
Create Date: 2026-03-06
"""
from __future__ import annotations

revision = "0008_merge_branches"
down_revision = ("0007_backfill_undata_url", "0006_fix_statfin_portal_key")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
