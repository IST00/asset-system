"""seed default measurement units

Revision ID: 019
Revises: 018
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None

_DEFAULT_UNITS = (
    ("TAI", "台"),
    ("GE", "个"),
    ("GEN", "根"),
    ("TAO", "套"),
    ("BU", "部"),
    ("JIAN", "件"),
    ("ZHANG", "张"),
    ("BA", "把"),
)


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(tz=timezone.utc)
    for code, name in _DEFAULT_UNITS:
        existing_code = (
            bind.execute(
                sa.text("SELECT code, name FROM units WHERE code = :code"),
                {"code": code},
            )
            .mappings()
            .first()
        )
        existing_name = (
            bind.execute(
                sa.text("SELECT code, name FROM units WHERE name = :name"),
                {"name": name},
            )
            .mappings()
            .first()
        )
        if existing_code is not None:
            if existing_code["code"] != code:
                raise RuntimeError(
                    f"默认计量单位冲突：默认编码 {code!r} 查询到"
                    f"现有编码 {existing_code['code']!r}，不能初始化"
                )
            if existing_code["name"] != name:
                raise RuntimeError(
                    f"默认计量单位冲突：编码 {code} "
                    f"已对应“{existing_code['name']}”，不能初始化为“{name}”"
                )
            continue
        if existing_name is not None:
            raise RuntimeError(
                f"默认计量单位冲突：名称“{name}”已使用编码 "
                f"{existing_name['code']}，不能初始化为 {code}"
            )

        bind.execute(
            sa.text(
                "INSERT INTO units "
                "(code, name, status, version, created_at, updated_at) "
                "VALUES (:code, :name, :status, :version, :now, :now)"
            ),
            {
                "code": code,
                "name": name,
                "status": "ENABLED",
                "version": 1,
                "now": now,
            },
        )


def downgrade() -> None:
    # Keep master data because business records may already reference these units.
    pass
