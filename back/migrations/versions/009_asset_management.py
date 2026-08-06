"""asset maintenance, lifecycle permissions and RFID

Revision ID: 009
Revises: 008
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None

_PERMISSIONS = (
    ("asset:edit", "编辑资产资料", "asset"),
    ("asset:relation:manage", "维护主附资产关系", "asset"),
    ("asset:transfer", "资产转移", "asset-lifecycle"),
    ("asset:repair", "资产维修", "asset-lifecycle"),
    ("asset:scrap", "资产报废", "asset-lifecycle"),
    ("public-object:manage", "管理公共使用对象", "master-data"),
)


def upgrade() -> None:
    with op.batch_alter_table("assets") as batch:
        batch.add_column(sa.Column("rfid_tag", sa.String(length=191), nullable=True))
        batch.create_unique_constraint("uq_assets_rfid_tag", ["rfid_tag"])
        batch.create_index("ix_assets_rfid_tag", ["rfid_tag"], unique=False)

    bind = op.get_bind()
    now = datetime.now(tz=timezone.utc)
    for code, name, module in _PERMISSIONS:
        permission_id = bind.scalar(
            sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code}
        )
        if permission_id is None:
            bind.execute(
                sa.text(
                    "INSERT INTO permissions (code, name, module, enabled, created_at, updated_at) VALUES (:code, :name, :module, 1, :now, :now)"
                ),
                {"code": code, "name": name, "module": module, "now": now},
            )
            permission_id = bind.scalar(
                sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code}
            )
        bind.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) SELECT r.id, :permission_id FROM roles r WHERE r.code IN ('SUPER_ADMIN', 'ASSET_ADMIN') AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = :permission_id)"
            ),
            {"permission_id": permission_id},
        )


def downgrade() -> None:
    bind = op.get_bind()
    codes = tuple(code for code, _name, _module in _PERMISSIONS)
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code IN :codes)"
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": codes},
    )
    bind.execute(
        sa.text("DELETE FROM permissions WHERE code IN :codes").bindparams(
            sa.bindparam("codes", expanding=True)
        ),
        {"codes": codes},
    )
    with op.batch_alter_table("assets") as batch:
        batch.drop_index("ix_assets_rfid_tag")
        batch.drop_constraint("uq_assets_rfid_tag", type_="unique")
        batch.drop_column("rfid_tag")
