"""approval transfer and reminder governance

Revision ID: 012
Revises: 011
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None

_PERMISSIONS = (
    ("approval:task:transfer", "转交待审批任务", "approval"),
    ("approval:task:remind", "催办待审批申请", "approval"),
)


def upgrade() -> None:
    with op.batch_alter_table("operation_requests") as batch_op:
        batch_op.add_column(
            sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("withdrawn_by", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("withdrawal_reason", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_operation_requests_withdrawn_by_users",
            "users",
            ["withdrawn_by"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_operation_requests_withdrawn_by", ["withdrawn_by"], unique=False
        )

    op.create_table(
        "approval_task_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("operation_request_id", sa.Integer(), nullable=False),
        sa.Column("approval_task_id", sa.Integer(), nullable=True),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("from_approver_id", sa.Integer(), nullable=True),
        sa.Column("to_approver_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_request_id"], ["operation_requests.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["approval_task_id"], ["approval_tasks.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["from_approver_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["to_approver_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_approval_task_events_operation_request_id",
        "approval_task_events",
        ["operation_request_id"],
    )
    op.create_index(
        "ix_approval_task_events_approval_task_id",
        "approval_task_events",
        ["approval_task_id"],
    )
    op.create_index(
        "ix_approval_task_events_actor_id", "approval_task_events", ["actor_id"]
    )
    op.create_index(
        "ix_approval_task_events_event_type",
        "approval_task_events",
        ["event_type"],
    )
    op.create_index(
        "ix_approval_task_events_from_approver_id",
        "approval_task_events",
        ["from_approver_id"],
    )
    op.create_index(
        "ix_approval_task_events_to_approver_id",
        "approval_task_events",
        ["to_approver_id"],
    )

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
                sa.text("SELECT id FROM permissions WHERE code = :code"),
                {"code": code},
            )
        bind.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) SELECT r.id, :permission_id FROM roles r WHERE r.code IN ('SUPER_ADMIN', 'ASSET_ADMIN') AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = :permission_id)"
            ),
            {"permission_id": permission_id},
        )


def downgrade() -> None:
    bind = op.get_bind()
    codes = tuple(item[0] for item in _PERMISSIONS)
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
    op.drop_index(
        "ix_approval_task_events_to_approver_id", table_name="approval_task_events"
    )
    op.drop_index(
        "ix_approval_task_events_from_approver_id", table_name="approval_task_events"
    )
    op.drop_index(
        "ix_approval_task_events_event_type", table_name="approval_task_events"
    )
    op.drop_index("ix_approval_task_events_actor_id", table_name="approval_task_events")
    op.drop_index(
        "ix_approval_task_events_approval_task_id", table_name="approval_task_events"
    )
    op.drop_index(
        "ix_approval_task_events_operation_request_id",
        table_name="approval_task_events",
    )
    op.drop_table("approval_task_events")
    with op.batch_alter_table("operation_requests") as batch_op:
        batch_op.drop_index("ix_operation_requests_withdrawn_by")
        batch_op.drop_constraint(
            "fk_operation_requests_withdrawn_by_users", type_="foreignkey"
        )
        batch_op.drop_column("withdrawal_reason")
        batch_op.drop_column("withdrawn_by")
        batch_op.drop_column("withdrawn_at")
