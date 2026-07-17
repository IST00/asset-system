from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path


BACK_DIR = Path(__file__).resolve().parents[1]
MIGRATION = BACK_DIR / "migrations" / "versions" / "002_backend_foundation.py"


def test_backend_foundation_migration_follows_initial_revision() -> None:
    assert MIGRATION.is_file()
    spec = importlib.util.spec_from_file_location("migration_002", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "002"
    assert module.down_revision == "001"


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
    assert "organization_id" in columns
    assert "role" not in columns

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
