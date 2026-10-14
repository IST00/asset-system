"""enforce one account role and built-in hierarchy

Revision ID: 040
Revises: 039
Create Date: 2026-10-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # Clean historical multi-role assignments by retaining only the highest
    # built-in role: SUPER_ADMIN > ASSET_ADMIN > USER.
    bind.execute(
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

    # The new business rule allows asset administrators to administer user
    # authorization, but not to grant SUPER_ADMIN.
    bind.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT roles.id, permissions.id FROM roles, permissions "
            "WHERE roles.code = 'ASSET_ADMIN' "
            "AND permissions.code IN ('system:role:view', 'system:role:manage') "
            "AND NOT EXISTS ("
            "SELECT 1 FROM role_permissions existing "
            "WHERE existing.role_id = roles.id "
            "AND existing.permission_id = permissions.id)"
        )
    )

    # Higher built-in roles inherit every permission granted to lower roles.
    bind.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT higher_role.id, lower_assignment.permission_id "
            "FROM role_permissions AS lower_assignment "
            "JOIN roles AS lower_role ON lower_role.id = lower_assignment.role_id "
            "JOIN roles AS higher_role ON ("
            "  (lower_role.code = 'ASSET_ADMIN' AND higher_role.code = 'SUPER_ADMIN')"
            "  OR (lower_role.code = 'USER' AND higher_role.code = 'ASSET_ADMIN')"
            "  OR (lower_role.code = 'USER' AND higher_role.code = 'SUPER_ADMIN')"
            ") "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM role_permissions AS existing "
            "  WHERE existing.role_id = higher_role.id "
            "  AND existing.permission_id = lower_assignment.permission_id)"
        )
    )


def downgrade() -> None:
    # The previous per-role permission assignments cannot be reconstructed
    # reliably after hierarchy inheritance has been applied.
    pass
