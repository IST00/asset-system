"""persistent asset exports and label files

Revision ID: 015
Revises: 014
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None

_PERMISSIONS = (
    ("asset:export", "导出资产台账", "asset"),
    ("asset:label:print", "生成资产标签", "asset"),
)


def _seed_permissions() -> None:
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


def upgrade() -> None:
    op.create_table(
        "export_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("filter_snapshot", sa.JSON(), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False, unique=True),
        sa.Column("mime_type", sa.String(length=191), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_export_jobs_job_type", "export_jobs", ["job_type"])
    op.create_index("ix_export_jobs_status", "export_jobs", ["status"])
    op.create_index("ix_export_jobs_created_by", "export_jobs", ["created_by"])
    op.create_index("ix_export_jobs_expires_at", "export_jobs", ["expires_at"])
    _seed_permissions()


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
    op.drop_index("ix_export_jobs_expires_at", table_name="export_jobs")
    op.drop_index("ix_export_jobs_created_by", table_name="export_jobs")
    op.drop_index("ix_export_jobs_status", table_name="export_jobs")
    op.drop_index("ix_export_jobs_job_type", table_name="export_jobs")
    op.drop_table("export_jobs")
