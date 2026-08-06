"""master-data tree export permissions

Revision ID: 017
Revises: 016
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None

_PERMISSIONS = (
    ("organization:export", "导出公司编码", "organization"),
    ("asset-category:export", "导出资产分类", "asset-category"),
)


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(tz=timezone.utc)
    for code, name, module in _PERMISSIONS:
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
    codes = [item[0] for item in _PERMISSIONS]
    placeholders = ", ".join(f":code_{index}" for index in range(len(codes)))
    params = {f"code_{index}": code for index, code in enumerate(codes)}
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            f"(SELECT id FROM permissions WHERE code IN ({placeholders}))"
        ),
        params,
    )
    bind.execute(
        sa.text(f"DELETE FROM permissions WHERE code IN ({placeholders})"), params
    )
