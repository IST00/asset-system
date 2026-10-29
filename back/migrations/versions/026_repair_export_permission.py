"""add repair record export permission

Revision ID: 026
Revises: 025
Create Date: 2026-09-03
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None

_PERMISSION = ("repair:export", "导出维修记录", "repair")


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(tz=timezone.utc)
    code, name, module = _PERMISSION
    permission_id = bind.scalar(
        sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code}
    )
    if permission_id is None:
        bind.execute(
            sa.text(
                "INSERT INTO permissions "
                "(code, name, module, enabled, created_at, updated_at) "
                "VALUES (:code, :name, :module, 1, :now, :now)"
            ),
            {"code": code, "name": name, "module": module, "now": now},
        )
    bind.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT roles.id, permissions.id FROM roles, permissions "
            "WHERE roles.code = 'SUPER_ADMIN' "
            "AND permissions.code = :permission "
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
