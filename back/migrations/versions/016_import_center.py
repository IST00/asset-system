"""server-side spreadsheet import center

Revision ID: 016
Revises: 015
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None

_PERMISSIONS = (
    ("asset:import", "导入资产台账", "asset"),
    ("organization:import", "导入公司编码", "organization"),
    ("asset-category:import", "导入资产分类", "asset-category"),
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
        "import_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_no", sa.String(length=64), nullable=False, unique=True),
        sa.Column("import_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("file_format", sa.String(length=16), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("create_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("update_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unchanged_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("preview_data", sa.JSON(), nullable=False),
        sa.Column("result_data", sa.JSON(), nullable=True),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "confirmed_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_import_jobs_job_no", "import_jobs", ["job_no"], unique=True)
    op.create_index("ix_import_jobs_import_type", "import_jobs", ["import_type"])
    op.create_index("ix_import_jobs_status", "import_jobs", ["status"])
    op.create_index("ix_import_jobs_created_by", "import_jobs", ["created_by"])
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
    op.drop_index("ix_import_jobs_created_by", table_name="import_jobs")
    op.drop_index("ix_import_jobs_status", table_name="import_jobs")
    op.drop_index("ix_import_jobs_import_type", table_name="import_jobs")
    op.drop_index("ix_import_jobs_job_no", table_name="import_jobs")
    op.drop_table("import_jobs")
