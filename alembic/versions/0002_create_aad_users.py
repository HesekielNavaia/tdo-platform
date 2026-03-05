"""Create Azure AD managed identity users for Container Apps Jobs

Revision ID: 0002_create_aad_users
Revises: 0001_initial_schema
Create Date: 2026-03-05
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0002_create_aad_users"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

# Managed identity names and OIDs from Azure portal
# These must match exactly as they appear in Azure AD
AAD_USERS = [
    # (display_name, object_id, is_admin)
    # OIDs are principalId values from `az identity list --resource-group tdo-platform-dev`
    ("tdo-id-harvest-dev",   "26192378-4d99-4306-9304-a06292e16d26", False),
    ("tdo-id-harmonise-dev", "fb623fbb-b3b0-4ef6-ad04-055bab8f7034", False),
    ("tdo-id-api-dev",       "c92226bc-809c-4358-aaa4-59bb75d8bb22", False),
]


def upgrade() -> None:
    # Managed identities are registered as Azure AD admins via the Azure Portal/CLI,
    # not via pgaadauth_create_principal_with_oid (which may not be available).
    # Azure AD admins already have full privileges so no GRANT statements needed.
    pass


def downgrade() -> None:
    pass
