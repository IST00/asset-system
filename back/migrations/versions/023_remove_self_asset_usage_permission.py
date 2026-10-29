"""remove self asset usage permission

Revision ID: 023
Revises: 022
Create Date: 2026-09-03
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None

_PERMISSION_CODE = "asset:usage:self"
_PERMISSION_NAME = "自行申请领用资产"
_ROLE_CODES = ("SUPER_ADMIN", "ASSET_ADMIN", "USER")


def upgrade() -> None:
    bind = op.get_bind()
    permission_id = bind.scalar(
        sa.text("SELECT id FROM permissions WHERE code = :code"),
        {"code": _PERMISSION_CODE},
    )
    if permission_id is None:
        return
    bind.execute(
        sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"),
        {"permission_id": permission_id},
    )
    bind.execute(
        sa.text("DELETE FROM permissions WHERE id = :permission_id"),
        {"permission_id": permission_id},
    )


def downgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(tz=timezone.utc)
    permission_id = bind.scalar(
        sa.text("SELECT id FROM permissions WHERE code = :code"),
        {"code": _PERMISSION_CODE},
    )
    if permission_id is None:
        bind.execute(
            sa.text(
                "INSERT INTO permissions "
                "(code, name, module, enabled, created_at, updated_at) "
                "VALUES (:code, :name, 'asset', 1, :now, :now)"
            ),
            {"code": _PERMISSION_CODE, "name": _PERMISSION_NAME, "now": now},
        )
        permission_id = bind.scalar(
            sa.text("SELECT id FROM permissions WHERE code = :code"),
            {"code": _PERMISSION_CODE},
        )

    for role_code in _ROLE_CODES:
        bind.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT roles.id, :permission_id FROM roles "
                "WHERE roles.code = :role_code AND NOT EXISTS ("
                "SELECT 1 FROM role_permissions "
                "WHERE role_permissions.role_id = roles.id "
                "AND role_permissions.permission_id = :permission_id)"
            ),
            {"permission_id": permission_id, "role_code": role_code},
        )
