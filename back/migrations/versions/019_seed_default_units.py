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
        if existing_code is not None or existing_name is not None:
            continue

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
