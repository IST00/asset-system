from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


BACK_DIR = Path(__file__).resolve().parents[1]
MIGRATION = BACK_DIR / "migrations" / "versions" / "019_seed_default_units.py"
DEFAULT_UNITS = [
    ("BA", "把", "ENABLED", 1),
    ("BU", "部", "ENABLED", 1),
    ("GE", "个", "ENABLED", 1),
    ("GEN", "根", "ENABLED", 1),
    ("JIAN", "件", "ENABLED", 1),
    ("TAI", "台", "ENABLED", 1),
    ("TAO", "套", "ENABLED", 1),
    ("ZHANG", "张", "ENABLED", 1),
]


def _migration_env(database: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "FLASK_APP": "manage.py",
            "FLASK_ENV": "dev",
            "DB_URL": f"sqlite:///{database}",
            "LOG_FILE_ENABLED": "false",
        }
    )
    return env


def _migrate(
    database: Path, command: str, revision: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "flask",
            "db",
            command,
            revision,
        ],
        cwd=BACK_DIR,
        env=_migration_env(database),
        capture_output=True,
        text=True,
        check=False,
    )


def _prepare_018(database: Path) -> None:
    result = _migrate(database, "upgrade", "018")
    assert result.returncode == 0, result.stdout + result.stderr


def _unit_rows(database: Path) -> list[tuple[str, str, str, int]]:
    with sqlite3.connect(database) as connection:
        return connection.execute(
            "SELECT code, name, status, version FROM units ORDER BY code"
        ).fetchall()


def test_default_unit_migration_follows_user_preferences() -> None:
    assert MIGRATION.is_file()
    spec = importlib.util.spec_from_file_location("migration_019", MIGRATION)
    if spec is None or spec.loader is None:
        pytest.fail("could not load migration 019")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "019"
    assert module.down_revision == "018"


def test_default_unit_migration_seeds_and_retains_units_on_downgrade(
    tmp_path: Path,
) -> None:
    database = tmp_path / "default-unit-migration.db"
    _prepare_018(database)
    assert _unit_rows(database) == []

    upgrade = _migrate(database, "upgrade", "019")
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr
    assert _unit_rows(database) == DEFAULT_UNITS

    downgrade = _migrate(database, "downgrade", "018")
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr
    assert _unit_rows(database) == DEFAULT_UNITS

    reupgrade = _migrate(database, "upgrade", "019")
    assert reupgrade.returncode == 0, reupgrade.stdout + reupgrade.stderr
    assert _unit_rows(database) == DEFAULT_UNITS


def test_default_unit_migration_preserves_identical_existing_unit(
    tmp_path: Path,
) -> None:
    database = tmp_path / "default-unit-migration.db"
    _prepare_018(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO units "
            "(code, name, status, version, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            ("TAI", "台", "DISABLED", 7),
        )

    upgrade = _migrate(database, "upgrade", "019")
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr

    with sqlite3.connect(database) as connection:
        unit = connection.execute(
            "SELECT code, name, status, version FROM units WHERE code = ?",
            ("TAI",),
        ).fetchone()
        count = connection.execute(
            "SELECT COUNT(*) FROM units WHERE code = ? OR name = ?",
            ("TAI", "台"),
        ).fetchone()[0]

    assert unit == ("TAI", "台", "DISABLED", 7)
    assert count == 1
