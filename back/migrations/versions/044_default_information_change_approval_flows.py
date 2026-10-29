"""Seed role-based internal approval flows for asset information changes."""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None

_OPERATION_TYPES = (
    "PHYSICAL_INFO_CHANGE",
    "FINANCIAL_INFO_CHANGE",
    "WARRANTY_INFO_CHANGE",
)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _seed_flow(bind: sa.engine.Connection, operation_type: str) -> None:
    definition_id = bind.scalar(
        sa.text(
            "SELECT id FROM approval_flow_definitions "
            "WHERE operation_type = :operation_type"
        ),
        {"operation_type": operation_type},
    )
    if definition_id is not None:
        return

    now = _utcnow()
    result = bind.execute(
        sa.text(
            "INSERT INTO approval_flow_definitions "
            "(operation_type, name, status, version, created_at, updated_at) "
            "VALUES (:operation_type, '资产信息变更审批', 'PUBLISHED', 1, :now, :now)"
        ),
        {"operation_type": operation_type, "now": now},
    )
    definition_id = result.lastrowid
    version_result = bind.execute(
        sa.text(
            "INSERT INTO approval_flow_versions "
            "(flow_definition_id, version_no, status, published_at, "
            "published_by, created_at, updated_at) "
            "VALUES (:definition_id, 1, 'PUBLISHED', :now, NULL, :now, :now)"
        ),
        {"definition_id": definition_id, "now": now},
    )
    version_id = version_result.lastrowid
    layer_result = bind.execute(
        sa.text(
            "INSERT INTO approval_flow_layers "
            "(flow_version_id, level_no, sign_mode, allow_self_approval, "
            "created_at, updated_at) "
            "VALUES (:version_id, 1, 'OR_SIGN', 1, :now, :now)"
        ),
        {"version_id": version_id, "now": now},
    )
    layer_id = layer_result.lastrowid
    role_ids = bind.scalars(
        sa.text("SELECT id FROM roles WHERE code IN ('SUPER_ADMIN', 'ASSET_ADMIN')")
    ).fetchall()
    for role_id in role_ids:
        bind.execute(
            sa.text(
                "INSERT INTO approval_flow_assignee_rules "
                "(layer_id, assignee_type, assignee_id, created_at, updated_at) "
                "VALUES (:layer_id, 'ROLE', :role_id, :now, :now)"
            ),
            {"layer_id": layer_id, "role_id": role_id, "now": now},
        )


def upgrade() -> None:
    bind = op.get_bind()
    for operation_type in _OPERATION_TYPES:
        _seed_flow(bind, operation_type)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM approval_flow_assignee_rules WHERE layer_id IN ("
            "SELECT layer_id FROM ("
            "SELECT afl.id AS layer_id "
            "FROM approval_flow_layers afl "
            "JOIN approval_flow_versions afv ON afv.id = afl.flow_version_id "
            "JOIN approval_flow_definitions afd ON afd.id = afv.flow_definition_id "
            "WHERE afd.operation_type IN :operation_types "
            "AND afd.name = '资产信息变更审批'"
            ") seeded_layers)"
        ).bindparams(sa.bindparam("operation_types", expanding=True)),
        {"operation_types": _OPERATION_TYPES},
    )
    bind.execute(
        sa.text(
            "DELETE FROM approval_flow_layers WHERE flow_version_id IN ("
            "SELECT version_id FROM ("
            "SELECT afv.id AS version_id "
            "FROM approval_flow_versions afv "
            "JOIN approval_flow_definitions afd "
            "ON afd.id = afv.flow_definition_id "
            "WHERE afd.operation_type IN :operation_types "
            "AND afd.name = '资产信息变更审批'"
            ") seeded_versions)"
        ).bindparams(sa.bindparam("operation_types", expanding=True)),
        {"operation_types": _OPERATION_TYPES},
    )
    bind.execute(
        sa.text(
            "DELETE FROM approval_flow_versions WHERE flow_definition_id IN ("
            "SELECT definition_id FROM ("
            "SELECT afd.id AS definition_id "
            "FROM approval_flow_definitions afd "
            "WHERE afd.operation_type IN :operation_types "
            "AND afd.name = '资产信息变更审批'"
            ") seeded_definitions)"
        ).bindparams(sa.bindparam("operation_types", expanding=True)),
        {"operation_types": _OPERATION_TYPES},
    )
    bind.execute(
        sa.text(
            "DELETE FROM approval_flow_definitions WHERE operation_type IN :operation_types "
            "AND name = '资产信息变更审批'"
        ).bindparams(sa.bindparam("operation_types", expanding=True)),
        {"operation_types": _OPERATION_TYPES},
    )
