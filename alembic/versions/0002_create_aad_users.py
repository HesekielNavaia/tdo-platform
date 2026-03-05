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
    conn = op.get_bind()
    for name, oid, is_admin in AAD_USERS:
        # pgaadauth_create_principal_with_oid(name, oid, role, is_superuser, is_replication)
        # role: 'service' for managed identity
        conn.execute(text(
            f"SELECT * FROM pgaadauth_create_principal_with_oid("
            f"'{name}', '{oid}', 'service', false, false)"
        ))
        conn.execute(text(f"GRANT ALL ON SCHEMA public TO \"{name}\""))
        conn.execute(text(f"GRANT ALL ON ALL TABLES IN SCHEMA public TO \"{name}\""))
        conn.execute(text(f"GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO \"{name}\""))
        conn.execute(text(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            f"GRANT ALL ON TABLES TO \"{name}\""
        ))


def downgrade() -> None:
    conn = op.get_bind()
    for name, _, _ in AAD_USERS:
        conn.execute(text(f"DROP ROLE IF EXISTS \"{name}\""))
