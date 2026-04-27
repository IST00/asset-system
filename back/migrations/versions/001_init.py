"""Initial migration: create users table + seed admin.

Revision ID: 001
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

# bcrypt hash of "admin123" (portable across Python/Java)
_ADMIN_HASH = "$2b$10$f0NJc81l7nI/lQ9tn9Xhqe7r3tt7ELbU12TG2n98n/1gsI5CxdZI6"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("password", sa.String(255), nullable=False),
        sa.Column("nickname", sa.String(64), nullable=True),
        sa.Column("role", sa.String(32), nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    now = datetime.now(tz=timezone.utc)
    op.execute(
        sa.text(
            "INSERT INTO users (username, password, nickname, role, enabled, created_at, updated_at) "
            "VALUES (:u, :p, :n, :r, 1, :ca, :ua)"
        ).bindparams(
            u="admin",
            p=_ADMIN_HASH,
            n="Admin",
            r="ADMIN",
            ca=now,
            ua=now,
        )
    )


def downgrade() -> None:
    op.drop_table("users")
