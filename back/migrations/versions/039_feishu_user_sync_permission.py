"""add user management permission for Feishu sync

Revision ID: 039
Revises: 038
Create Date: 2026-10-09
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None

_PERMISSION = ("user:manage", "管理用户", "system")


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(tz=timezone.utc)
    code, name, module = _PERMISSION
    bind.execute(
        sa.text(
            "INSERT INTO permissions "
            "(code, name, module, enabled, created_at, updated_at) "
            "SELECT :code, :name, :module, 1, :now, :now "
            "WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :code)"
        ),
        {"code": code, "name": name, "module": module, "now": now},
    )
    bind.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT roles.id, permissions.id FROM roles, permissions "
            "WHERE roles.code IN ('SUPER_ADMIN', 'ASSET_ADMIN') AND permissions.code = :permission "
            "AND NOT EXISTS ("
            "SELECT 1 FROM role_permissions existing "
            "WHERE existing.role_id = roles.id "
            "AND existing.permission_id = permissions.id)"
        ),
        {"permission": code},
    )


def downgrade() -> None:
    bind = op.get_bind()
    code = _PERMISSION[0]
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE code = :code)"
        ),
        {"code": code},
    )
    bind.execute(sa.text("DELETE FROM permissions WHERE code = :code"), {"code": code})
