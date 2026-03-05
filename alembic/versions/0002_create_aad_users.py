"""Create Azure AD managed identity users for Container Apps Jobs

Revision ID: 0002_create_aad_users
Revises: 0001_initial_schema
Create Date: 2026-03-05
"""
from __future__ import annotations

from alembic import op

revision = "0002_create_aad_users"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

# Managed identity names and OIDs from Azure portal
# These must match exactly as they appear in Azure AD
AAD_USERS = [
    # (display_name, object_id, is_admin)
    ("tdo-id-harvest-dev",   "26192378-4d99-4306-9304-a06292e16d26", False),
    ("tdo-id-harmonise-dev", "33df6bf8-3d72-4215-8e59-e7ce686da107", False),
    ("tdo-id-api-dev",       "e7454e98-e87a-4887-adbb-ad605a0b7f62", False),
]


def upgrade() -> None:
    conn = op.get_bind()
    for name, oid, is_admin in AAD_USERS:
        # pgaadauth_create_principal_with_oid(name, oid, role, is_superuser, is_replication)
        # role: 'service' for managed identity
        conn.execute(
            f"SELECT * FROM pgaadauth_create_principal_with_oid("
            f"'{name}', '{oid}', 'service', false, false)"
        )
        conn.execute(f"GRANT ALL ON SCHEMA public TO \"{name}\"")
        conn.execute(f"GRANT ALL ON ALL TABLES IN SCHEMA public TO \"{name}\"")
        conn.execute(f"GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO \"{name}\"")
        conn.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            f"GRANT ALL ON TABLES TO \"{name}\""
        )


def downgrade() -> None:
    conn = op.get_bind()
    for name, _, _ in AAD_USERS:
        conn.execute(f"DROP ROLE IF EXISTS \"{name}\"")
