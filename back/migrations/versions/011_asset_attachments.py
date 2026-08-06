"""asset attachment metadata and local storage permission

Revision ID: 011
Revises: 010
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None

_PERMISSION = ("asset:attachment:manage", "管理资产照片和附件", "asset")


def upgrade() -> None:
    op.create_table(
        "asset_attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("business_type", sa.String(length=32), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("is_cover", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="ACTIVE"
        ),
        sa.Column("uploaded_by", sa.Integer(), nullable=False),
        sa.Column("voided_by", sa.Integer(), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["voided_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_asset_attachments_storage_key"),
    )
    op.create_index("ix_asset_attachments_asset_id", "asset_attachments", ["asset_id"])
    op.create_index(
        "ix_asset_attachments_business_type", "asset_attachments", ["business_type"]
    )
    op.create_index("ix_asset_attachments_sha256", "asset_attachments", ["sha256"])
    op.create_index("ix_asset_attachments_status", "asset_attachments", ["status"])
    op.create_index(
        "ix_asset_attachments_storage_key", "asset_attachments", ["storage_key"]
    )
    op.create_index(
        "ix_asset_attachments_uploaded_by", "asset_attachments", ["uploaded_by"]
    )
    op.create_index(
        "ix_asset_attachments_voided_by", "asset_attachments", ["voided_by"]
    )

    bind = op.get_bind()
    code, name, module = _PERMISSION
    now = datetime.now(tz=timezone.utc)
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
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code = :code)"
        ),
        {"code": _PERMISSION[0]},
    )
    bind.execute(
        sa.text("DELETE FROM permissions WHERE code = :code"), {"code": _PERMISSION[0]}
    )
    op.drop_index("ix_asset_attachments_voided_by", table_name="asset_attachments")
    op.drop_index("ix_asset_attachments_uploaded_by", table_name="asset_attachments")
    op.drop_index("ix_asset_attachments_storage_key", table_name="asset_attachments")
    op.drop_index("ix_asset_attachments_status", table_name="asset_attachments")
    op.drop_index("ix_asset_attachments_sha256", table_name="asset_attachments")
    op.drop_index("ix_asset_attachments_business_type", table_name="asset_attachments")
    op.drop_index("ix_asset_attachments_asset_id", table_name="asset_attachments")
    op.drop_table("asset_attachments")
