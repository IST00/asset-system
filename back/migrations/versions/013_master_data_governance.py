"""master-data deletion governance and automatic location codes

Revision ID: 013
Revises: 012
"""

from __future__ import annotations

from datetime import datetime, timezone
import re

from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None

_PERMISSIONS = (
    ("location:delete", "删除未使用地点", "location"),
    ("asset-category:delete", "删除未使用资产分类", "asset-category"),
)
_LOCATION_CODE_PATTERN = re.compile(r"^LOC(\d+)$")


def _seed_location_sequence() -> None:
    bind = op.get_bind()
    maximum = 0
    for code in bind.scalars(sa.text("SELECT code FROM asset_locations")):
        match = _LOCATION_CODE_PATTERN.fullmatch(str(code))
        if match is not None:
            maximum = max(maximum, int(match.group(1)))
    now = datetime.now(tz=timezone.utc)
    bind.execute(
        sa.text(
            "INSERT INTO location_code_sequences "
            "(prefix, current_value, created_at, updated_at) "
            "VALUES (:prefix, :current_value, :now, :now)"
        ),
        {"prefix": "LOC", "current_value": maximum, "now": now},
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
        "location_code_sequences",
        sa.Column("prefix", sa.String(length=16), nullable=False),
        sa.Column("current_value", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("prefix"),
    )
    _seed_location_sequence()
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
    op.drop_table("location_code_sequences")
