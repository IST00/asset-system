from __future__ import annotations

import importlib.util
import os
import sqlite3
import subprocess
from pathlib import Path


BACK_DIR = Path(__file__).resolve().parents[1]
MIGRATION = BACK_DIR / "migrations" / "versions" / "002_backend_foundation.py"
OPERATION_MIGRATION = (
    BACK_DIR / "migrations" / "versions" / "003_operation_foundation.py"
)
CONTRACT_MIGRATION = (
    BACK_DIR / "migrations" / "versions" / "004_operation_contract_freeze.py"
)


def test_backend_foundation_migration_follows_initial_revision() -> None:
    assert MIGRATION.is_file()
    spec = importlib.util.spec_from_file_location("migration_002", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "002"
    assert module.down_revision == "001"


def test_operation_foundation_migration_follows_backend_foundation() -> None:
    assert OPERATION_MIGRATION.is_file()
    spec = importlib.util.spec_from_file_location("migration_003", OPERATION_MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "003"
    assert module.down_revision == "002"


def test_operation_contract_migration_follows_operation_foundation() -> None:
    assert CONTRACT_MIGRATION.is_file()
    spec = importlib.util.spec_from_file_location("migration_004", CONTRACT_MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "004"
    assert module.down_revision == "003"


def test_migrations_upgrade_clean_sqlite_database(tmp_path) -> None:
    database = tmp_path / "migration.db"
    env = os.environ.copy()
    env.update(
        {
            "FLASK_APP": "manage.py",
            "FLASK_ENV": "dev",
            "DB_URL": f"sqlite:///{database}",
            "LOG_FILE_ENABLED": "false",
        }
    )
    result = subprocess.run(
        [str(BACK_DIR / ".venv" / "bin" / "flask"), "db", "upgrade"],
        cwd=BACK_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    import sqlite3

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
    assert {"roles", "permissions", "assets", "operation_requests"} <= tables
    assert {
        "public_usage_objects",
        "operation_request_assets",
        "asset_business_locks",
        "operation_execution_attempts",
        "external_approval_events",
        "operation_action_idempotencies",
        "approval_flow_definitions",
        "approval_flow_versions",
        "approval_flow_layers",
        "approval_flow_assignee_rules",
    } <= tables
    assert "organization_id" in columns
    assert "role" not in columns

    with sqlite3.connect(database) as connection:
        asset_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(assets)").fetchall()
        }
        operation_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(operation_requests)"
            ).fetchall()
        }
        stock_in_flow = connection.execute(
            "SELECT d.operation_type, v.version_no, l.level_no, r.assignee_type "
            "FROM approval_flow_definitions d "
            "JOIN approval_flow_versions v ON v.flow_definition_id = d.id "
            "JOIN approval_flow_layers l ON l.flow_version_id = v.id "
            "JOIN approval_flow_assignee_rules r ON r.layer_id = l.id "
            "WHERE d.operation_type = 'STOCK_IN'"
        ).fetchone()
    assert {
        "usage_type",
        "holder_user_id",
        "public_object_id",
        "usage_department_id",
        "parent_asset_id",
    } <= asset_columns
    assert {
        "parent_request_id",
        "approval_channel",
        "approval_execution_mode",
        "approval_flow_version_id",
        "external_instance_id",
        "idempotency_key",
        "terminated_at",
        "terminated_by",
        "termination_reason",
    } <= operation_columns
    assert stock_in_flow == ("STOCK_IN", 1, 1, "ROLE")

    with sqlite3.connect(database) as connection:
        cursor = connection.execute(
            "INSERT INTO users "
            "(username, password, nickname, organization_id, enabled, created_at, updated_at) "
            "VALUES (?, ?, ?, NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            ("downgrade-user", "x", "Downgrade User"),
        )
        connection.execute(
            "INSERT INTO user_roles (user_id, role_id) VALUES (?, 3)",
            (cursor.lastrowid,),
        )
        connection.commit()

    downgrade = subprocess.run(
        [str(BACK_DIR / ".venv" / "bin" / "flask"), "db", "downgrade", "001"],
        cwd=BACK_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr
    with sqlite3.connect(database) as connection:
        downgraded_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        downgraded_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
        downgraded_roles = dict(
            connection.execute(
                "SELECT username, role FROM users ORDER BY username"
            ).fetchall()
        )
    assert "assets" not in downgraded_tables
    assert "role" in downgraded_columns
    assert "organization_id" not in downgraded_columns
    assert downgraded_roles["admin"] == "ADMIN"
    assert downgraded_roles["downgrade-user"] == "USER"


def test_contract_migration_defaults_old_rows_and_downgrades_without_loss(
    tmp_path,
) -> None:
    database = tmp_path / "contract-migration.db"
    env = os.environ.copy()
    env.update(
        {
            "FLASK_APP": "manage.py",
            "FLASK_ENV": "dev",
            "DB_URL": f"sqlite:///{database}",
            "LOG_FILE_ENABLED": "false",
        }
    )
    upgrade_003 = subprocess.run(
        [str(BACK_DIR / ".venv" / "bin" / "flask"), "db", "upgrade", "003"],
        cwd=BACK_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert upgrade_003.returncode == 0, upgrade_003.stdout + upgrade_003.stderr
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO operation_requests "
            "(request_no, operation_type, applicant_id, approval_channel, "
            "approval_status, execution_status, flow_version, version, "
            "created_at, updated_at) VALUES "
            "('MIGRATION-004', 'STOCK_IN', 1, 'INTERNAL', 'PENDING', "
            "'NOT_STARTED', 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.commit()

    upgrade_004 = subprocess.run(
        [str(BACK_DIR / ".venv" / "bin" / "flask"), "db", "upgrade", "004"],
        cwd=BACK_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert upgrade_004.returncode == 0, upgrade_004.stdout + upgrade_004.stderr
    with sqlite3.connect(database) as connection:
        mode = connection.execute(
            "SELECT approval_execution_mode FROM operation_requests "
            "WHERE request_no = 'MIGRATION-004'"
        ).fetchone()
    assert mode == ("AUTO_ON_APPROVAL",)

    downgrade = subprocess.run(
        [str(BACK_DIR / ".venv" / "bin" / "flask"), "db", "downgrade", "003"],
        cwd=BACK_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr
    with sqlite3.connect(database) as connection:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(operation_requests)"
            ).fetchall()
        }
        request_no = connection.execute(
            "SELECT request_no FROM operation_requests "
            "WHERE request_no = 'MIGRATION-004'"
        ).fetchone()
    assert "approval_execution_mode" not in columns
    assert request_no == ("MIGRATION-004",)


def test_downgrade_preserves_all_and_sign_approval_records(tmp_path) -> None:
    database = tmp_path / "and-sign-downgrade.db"
    env = os.environ.copy()
    env.update(
        {
            "FLASK_APP": "manage.py",
            "FLASK_ENV": "dev",
            "DB_URL": f"sqlite:///{database}",
            "LOG_FILE_ENABLED": "false",
        }
    )
    upgrade = subprocess.run(
        [str(BACK_DIR / ".venv" / "bin" / "flask"), "db", "upgrade"],
        cwd=BACK_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr

    with sqlite3.connect(database) as connection:
        second_user = connection.execute(
            "INSERT INTO users "
            "(username, password, nickname, organization_id, enabled, created_at, updated_at) "
            "VALUES ('and-sign-reviewer', 'x', '会签人', NULL, 1, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ).lastrowid
        operation_id = connection.execute(
            "INSERT INTO operation_requests "
            "(request_no, operation_type, applicant_id, approval_channel, "
            "approval_status, execution_status, flow_version, version, "
            "created_at, updated_at) VALUES "
            "('DOWNGRADE-AND', 'TRANSFER', 1, 'INTERNAL', 'APPROVED', "
            "'NOT_STARTED', 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ).lastrowid
        step_id = connection.execute(
            "INSERT INTO approval_steps "
            "(operation_request_id, flow_layer_id, level_no, sign_mode, status, "
            "version, created_at, updated_at) VALUES "
            "(?, NULL, 1, 'AND_SIGN', 'APPROVED', 1, CURRENT_TIMESTAMP, "
            "CURRENT_TIMESTAMP)",
            (operation_id,),
        ).lastrowid
        first_task = connection.execute(
            "INSERT INTO approval_tasks "
            "(approval_step_id, approver_id, status, version, opinion, decided_at, "
            "created_at, updated_at) VALUES "
            "(?, 1, 'APPROVED', 1, '同意', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
            "CURRENT_TIMESTAMP)",
            (step_id,),
        ).lastrowid
        second_task = connection.execute(
            "INSERT INTO approval_tasks "
            "(approval_step_id, approver_id, status, version, opinion, decided_at, "
            "created_at, updated_at) VALUES "
            "(?, ?, 'APPROVED', 1, '同意', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
            "CURRENT_TIMESTAMP)",
            (step_id, second_user),
        ).lastrowid
        connection.executemany(
            "INSERT INTO approval_records "
            "(operation_request_id, approval_step_id, approval_task_id, actor_id, "
            "action, opinion, created_at, updated_at) VALUES "
            "(?, ?, ?, ?, 'APPROVE', '同意', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            [
                (operation_id, step_id, first_task, 1),
                (operation_id, step_id, second_task, second_user),
            ],
        )
        connection.commit()

    downgrade = subprocess.run(
        [str(BACK_DIR / ".venv" / "bin" / "flask"), "db", "downgrade", "002"],
        cwd=BACK_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr

    with sqlite3.connect(database) as connection:
        records = connection.execute(
            "SELECT approval_step_id, approval_task_id FROM approval_records "
            "WHERE operation_request_id = ? ORDER BY id",
            (operation_id,),
        ).fetchall()
        task_steps = dict(
            connection.execute(
                "SELECT id, approval_step_id FROM approval_tasks WHERE id IN (?, ?)",
                (first_task, second_task),
            ).fetchall()
        )
    assert len(records) == 2
    assert len({record[0] for record in records}) == 2
    assert all(task_steps[task_id] == step_id for step_id, task_id in records)
