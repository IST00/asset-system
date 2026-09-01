"""Deployment preflight contracts for pilot/production DB isolation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_environment_isolation.py"


def _write_env(path: Path, *, user: str, database: str) -> None:
    path.write_text(
        f"DB_HOST=db.example.com\nDB_USER={user}\n"
        f"DB_PASSWORD=not-printed\nDB_NAME={database}\n",
        encoding="utf-8",
    )


def test_distinct_database_user_and_name_are_accepted(tmp_path: Path) -> None:
    pilot = tmp_path / "pilot.env"
    production = tmp_path / "production.env"
    _write_env(pilot, user="asset_pilot_app", database="asset_system_pilot")
    _write_env(production, user="asset_prod_app", database="asset_system_prod")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(pilot), str(production)],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0
    assert "password" not in result.stdout.lower()
    assert "not-printed" not in result.stdout
    assert "not-printed" not in result.stderr


def test_shared_database_identity_is_rejected(tmp_path: Path) -> None:
    pilot = tmp_path / "pilot.env"
    production = tmp_path / "production.env"
    _write_env(pilot, user="shared_app", database="shared_database")
    _write_env(production, user="shared_app", database="shared_database")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(pilot), str(production)],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 1
    assert "DB_USER" in result.stderr
    assert "DB_NAME" in result.stderr
    assert "not-printed" not in result.stderr


def test_missing_database_identity_is_rejected_without_values(tmp_path: Path) -> None:
    pilot = tmp_path / "pilot.env"
    production = tmp_path / "production.env"
    pilot.write_text("DB_PASSWORD=not-printed\n", encoding="utf-8")
    _write_env(production, user="asset_prod_app", database="asset_system_prod")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(pilot), str(production)],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 2
    assert "DB_USER" in result.stderr
    assert "not-printed" not in result.stderr
