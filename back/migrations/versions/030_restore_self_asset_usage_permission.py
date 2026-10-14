"""restore employee self-service asset usage permission"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None

_PERMISSION_CODE = "asset:usage:self"
_PERMISSION_NAME = "自行申请资产领用和借用"


def upgrade() -> None:
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
    else:
        bind.execute(
            sa.text(
                "UPDATE permissions SET name = :name, module = 'asset', enabled = 1, "
                "updated_at = :now WHERE id = :permission_id"
            ),
            {
                "permission_id": permission_id,
                "name": _PERMISSION_NAME,
                "now": now,
            },
        )

    bind.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT roles.id, :permission_id FROM roles "
            "WHERE roles.code IN ('SUPER_ADMIN', 'ASSET_ADMIN', 'USER') "
            "AND NOT EXISTS (SELECT 1 FROM role_permissions "
            "WHERE role_permissions.role_id = roles.id "
            "AND role_permissions.permission_id = :permission_id)"
        ),
        {"permission_id": permission_id},
    )


def downgrade() -> None:
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
