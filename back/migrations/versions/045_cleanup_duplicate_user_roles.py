"""Clean duplicate built-in role assignments introduced by Feishu sync."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep only the highest built-in role per account. Custom roles are left
    # untouched; their assignment rules continue to be governed by RBAC APIs.
    op.get_bind().execute(
        sa.text(
            "DELETE FROM user_roles WHERE id IN ("
            "SELECT current_assignment.id "
            "FROM user_roles AS current_assignment "
            "JOIN roles AS current_role ON current_role.id = current_assignment.role_id "
            "JOIN user_roles AS higher_assignment "
            "  ON higher_assignment.user_id = current_assignment.user_id "
            "JOIN roles AS higher_role ON higher_role.id = higher_assignment.role_id "
            "WHERE ("
            "  (current_role.code = 'ASSET_ADMIN' AND higher_role.code = 'SUPER_ADMIN')"
            "  OR (current_role.code = 'USER' AND higher_role.code = 'ASSET_ADMIN')"
            "  OR (current_role.code = 'USER' AND higher_role.code = 'SUPER_ADMIN')"
            "))"
        )
    )


def downgrade() -> None:
    # Downgrading would require re-introducing known-duplicate historical role
    # assignments, which is unsafe to reconstruct automatically.
    pass
