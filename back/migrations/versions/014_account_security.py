"""local account security, password history, sessions, and rate limits

Revision ID: 014
Revises: 013
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "failed_login_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.add_column(sa.Column("locked_until", sa.DateTime(timezone=True)))
        batch_op.add_column(
            sa.Column(
                "must_change_password",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.add_column(
            sa.Column("password_changed_at", sa.DateTime(timezone=True))
        )
        batch_op.add_column(sa.Column("last_login_at", sa.DateTime(timezone=True)))

    op.create_table(
        "password_histories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_password_histories_user_id", "password_histories", ["user_id"])
    op.create_index(
        "ix_password_histories_created_at", "password_histories", ["created_at"]
    )

    op.create_table(
        "user_sessions",
        sa.Column("session_id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoke_reason", sa.String(length=128)),
        sa.Column("ip_address", sa.String(length=64)),
        sa.Column("user_agent", sa.String(length=255)),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_last_seen_at", "user_sessions", ["last_seen_at"])
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])
    op.create_index("ix_user_sessions_revoked_at", "user_sessions", ["revoked_at"])

    op.create_table(
        "security_event_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("username", sa.String(length=64)),
        sa.Column("ip_address", sa.String(length=64)),
        sa.Column("detail", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_security_event_logs_event_type", "security_event_logs", ["event_type"]
    )
    op.create_index(
        "ix_security_event_logs_user_id", "security_event_logs", ["user_id"]
    )
    op.create_index(
        "ix_security_event_logs_username", "security_event_logs", ["username"]
    )
    op.create_index(
        "ix_security_event_logs_created_at", "security_event_logs", ["created_at"]
    )

    op.create_table(
        "rate_limit_buckets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=128), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "scope", "subject", "window_start", name="uq_rate_limit_bucket"
        ),
    )
    op.create_index("ix_rate_limit_expiry", "rate_limit_buckets", ["expires_at"])

    bind = op.get_bind()
    now = datetime.now(tz=timezone.utc)
    bind.execute(sa.text("UPDATE users SET must_change_password = 1"))
    bind.execute(
        sa.text(
            "INSERT INTO password_histories (user_id, password_hash, created_at) "
            "SELECT id, password, :now FROM users"
        ),
        {"now": now},
    )


def downgrade() -> None:
    op.drop_index("ix_rate_limit_expiry", table_name="rate_limit_buckets")
    op.drop_table("rate_limit_buckets")
    op.drop_index("ix_security_event_logs_created_at", table_name="security_event_logs")
    op.drop_index("ix_security_event_logs_username", table_name="security_event_logs")
    op.drop_index("ix_security_event_logs_user_id", table_name="security_event_logs")
    op.drop_index("ix_security_event_logs_event_type", table_name="security_event_logs")
    op.drop_table("security_event_logs")
    op.drop_index("ix_user_sessions_revoked_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_last_seen_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("ix_password_histories_created_at", table_name="password_histories")
    op.drop_index("ix_password_histories_user_id", table_name="password_histories")
    op.drop_table("password_histories")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("last_login_at")
        batch_op.drop_column("password_changed_at")
        batch_op.drop_column("must_change_password")
        batch_op.drop_column("locked_until")
        batch_op.drop_column("failed_login_count")
