# Default Unit Seeds Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Alembic data migration that safely seeds the default measurement units required by asset-category imports.

**Architecture:** Revision `019` owns default-unit initialization and uses SQLAlchemy Core through Alembic, without importing runtime models or services. Focused migration tests exercise a real SQLite database at revision `018`, while the existing import API test records the contract that the downloaded category template is valid when `TAI` exists.

**Tech Stack:** Python 3.12/3.13, Flask 3, SQLAlchemy 2, Alembic, SQLite, Pytest, Ruff, Mypy.

---

## File map

- Create `back/migrations/versions/019_seed_default_units.py`: seed defaults, preserve identical records, reject semantic conflicts, retain master data on downgrade.
- Create `back/tests/test_default_unit_migration.py`: test revision linkage and migration behavior through real Alembic commands.
- Modify `back/tests/test_imports_api.py`: record the initialized-environment contract for the category template.

### Task 1: Establish the missing-migration failure

**Files:**
- Create: `back/tests/test_default_unit_migration.py`

- [ ] **Step 1: Write the failing revision and fresh-database tests**

Create `back/tests/test_default_unit_migration.py`:

```python
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess

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
            str(BACK_DIR / ".venv" / "bin" / "flask"),
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
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "019"
    assert module.down_revision == "018"


def test_default_unit_migration_seeds_and_retains_units_on_downgrade(
    tmp_path: Path,
) -> None:
    database = tmp_path / "default-units.db"
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
```

- [ ] **Step 2: Run and verify RED**

Run: `cd back && .venv/bin/pytest tests/test_default_unit_migration.py -v`

Expected: tests fail because `019_seed_default_units.py` and revision `019` do not exist.

### Task 2: Seed defaults on a fresh database

**Files:**
- Create: `back/migrations/versions/019_seed_default_units.py`
- Test: `back/tests/test_default_unit_migration.py`

- [ ] **Step 1: Add the minimal migration**

Create `back/migrations/versions/019_seed_default_units.py`:

```python
"""seed default measurement units

Revision ID: 019
Revises: 018
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None

_DEFAULT_UNITS = (
    ("TAI", "台"),
    ("GE", "个"),
    ("GEN", "根"),
    ("TAO", "套"),
    ("BU", "部"),
    ("JIAN", "件"),
    ("ZHANG", "张"),
    ("BA", "把"),
)


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(tz=timezone.utc)
    for code, name in _DEFAULT_UNITS:
        bind.execute(
            sa.text(
                "INSERT INTO units "
                "(code, name, status, version, created_at, updated_at) "
                "VALUES (:code, :name, 'ENABLED', 1, :now, :now)"
            ),
            {"code": code, "name": name, "now": now},
        )


def downgrade() -> None:
    # Preserve master data that may already be referenced by business rows.
    pass
```

- [ ] **Step 2: Run the two tests**

Run: `cd back && .venv/bin/pytest tests/test_default_unit_migration.py -v`

Expected: revision and initial upgrade assertions pass, while re-upgrade fails with a unique constraint. This exposes the next missing behavior.

### Task 3: Preserve identical existing units

**Files:**
- Modify: `back/tests/test_default_unit_migration.py`
- Modify: `back/migrations/versions/019_seed_default_units.py`

- [ ] **Step 1: Add a failing preservation test**

Append:

```python
def test_default_unit_migration_preserves_identical_existing_unit(
    tmp_path: Path,
) -> None:
    database = tmp_path / "existing-default-unit.db"
    _prepare_018(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO units "
            "(code, name, status, version, created_at, updated_at) "
            "VALUES ('TAI', '台', 'DISABLED', 7, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.commit()

    upgrade = _migrate(database, "upgrade", "019")
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr
    with sqlite3.connect(database) as connection:
        tai = connection.execute(
            "SELECT code, name, status, version FROM units WHERE code = 'TAI'"
        ).fetchone()
        count = connection.execute(
            "SELECT COUNT(*) FROM units WHERE code = 'TAI' OR name = '台'"
        ).fetchone()[0]
    assert tai == ("TAI", "台", "DISABLED", 7)
    assert count == 1
```

- [ ] **Step 2: Verify RED**

Run: `cd back && .venv/bin/pytest tests/test_default_unit_migration.py::test_default_unit_migration_preserves_identical_existing_unit -v`

Expected: FAIL with the `units.code` or `units.name` unique constraint.

- [ ] **Step 3: Implement the minimal skip behavior**

Before the insert in `upgrade()`, add:

```python
        existing_code = bind.execute(
            sa.text("SELECT code, name FROM units WHERE code = :code"),
            {"code": code},
        ).mappings().first()
        existing_name = bind.execute(
            sa.text("SELECT code, name FROM units WHERE name = :name"),
            {"name": name},
        ).mappings().first()
        if existing_code is not None or existing_name is not None:
            continue
```

- [ ] **Step 4: Verify GREEN**

Run: `cd back && .venv/bin/pytest tests/test_default_unit_migration.py -v`

Expected: 3 passed, including downgrade/re-upgrade without duplicates.

- [ ] **Step 5: Commit**

```bash
git add back/migrations/versions/019_seed_default_units.py back/tests/test_default_unit_migration.py
git commit -m "fix: seed default measurement units"
```

### Task 4: Reject semantic conflicts

**Files:**
- Modify: `back/tests/test_default_unit_migration.py`
- Modify: `back/migrations/versions/019_seed_default_units.py`

- [ ] **Step 1: Add failing conflict tests**

Append:

```python
@pytest.mark.parametrize(
    ("existing_code", "existing_name", "expected_message"),
    [
        ("TAI", "设备台", "编码 TAI 已对应“设备台”"),
        ("CUSTOM", "台", "名称“台”已使用编码 CUSTOM"),
    ],
)
def test_default_unit_migration_rejects_semantic_conflicts(
    tmp_path: Path,
    existing_code: str,
    existing_name: str,
    expected_message: str,
) -> None:
    database = tmp_path / f"conflict-{existing_code}.db"
    _prepare_018(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO units "
            "(code, name, status, version, created_at, updated_at) "
            "VALUES (?, ?, 'ENABLED', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (existing_code, existing_name),
        )
        connection.commit()

    upgrade = _migrate(database, "upgrade", "019")
    assert upgrade.returncode != 0
    assert expected_message in upgrade.stdout + upgrade.stderr
```

- [ ] **Step 2: Verify RED**

Run: `cd back && .venv/bin/pytest tests/test_default_unit_migration.py::test_default_unit_migration_rejects_semantic_conflicts -v`

Expected: both cases FAIL because the skip behavior silently accepts conflicts.

- [ ] **Step 3: Replace the skip with conflict detection**

Replace the three-line skip with:

```python
        if existing_code is not None:
            if existing_code["name"] != name:
                raise RuntimeError(
                    "默认计量单位冲突："
                    f"编码 {code} 已对应“{existing_code['name']}”，"
                    f"不能初始化为“{name}”"
                )
            continue
        if existing_name is not None:
            raise RuntimeError(
                "默认计量单位冲突："
                f"名称“{name}”已使用编码 {existing_name['code']}，"
                f"不能初始化为 {code}"
            )
```

- [ ] **Step 4: Verify GREEN**

Run: `cd back && .venv/bin/pytest tests/test_default_unit_migration.py -v`

Expected: 5 passed; the parametrized conflict test contributes two cases.

- [ ] **Step 5: Commit**

```bash
git add back/migrations/versions/019_seed_default_units.py back/tests/test_default_unit_migration.py
git commit -m "test: cover default unit seed conflicts"
```

### Task 5: Record the initialized import-template contract

**Files:**
- Modify: `back/tests/test_imports_api.py:93`

- [ ] **Step 1: Replace the empty-dictionary expectation**

Replace `test_category_xlsx_template_can_be_uploaded_and_reports_validation_errors` with:

```python
def test_category_xlsx_template_accepts_seeded_default_unit(client) -> None:
    _, headers = _actor(client, ["asset-category:import"])
    db.session.add(Unit(code="TAI", name="台", status="ENABLED"))
    db.session.commit()

    template = client.get("/api/v1/imports/templates/CATEGORY", headers=headers)
    assert template.status_code == 200
    assert template.data.startswith(b"PK")

    response = _upload(client, headers, "CATEGORY", template.data, "category.xlsx")
    assert response.status_code == 200
    preview = response.get_json()["data"]
    assert preview["status"] == "PREVIEW_READY"
    assert preview["error_count"] == 0
    assert preview["create_count"] == 1
    assert preview["rows"][0]["normalized"]["default_unit_id"] is not None
```

- [ ] **Step 2: Run focused import tests**

Run:

```bash
cd back && .venv/bin/pytest \
  tests/test_imports_api.py::test_category_xlsx_template_accepts_seeded_default_unit \
  tests/test_imports_api.py::test_category_master_data_export_preserves_tree_and_unit_code -v
```

Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
git add back/tests/test_imports_api.py
git commit -m "test: verify category template with seeded unit"
```

### Task 6: Run repository verification

**Files:**
- Verify only.

- [ ] **Step 1: Run focused tests**

Run: `cd back && .venv/bin/pytest tests/test_default_unit_migration.py tests/test_imports_api.py -v`

Expected: all tests pass.

- [ ] **Step 2: Run lint and formatting**

Run: `cd back && .venv/bin/ruff check . && .venv/bin/ruff format --check .`

Expected: exit 0 with no warnings.

- [ ] **Step 3: Run type checking**

Run: `cd back && .venv/bin/mypy app/ config.py`

Expected: exit 0 with no type errors.

- [ ] **Step 4: Run the complete backend suite**

Run: `cd back && .venv/bin/pytest`

Expected: exit 0 with zero failures.

- [ ] **Step 5: Confirm the final diff is scoped**

```bash
git diff main...HEAD --check
git status --short
```

Expected: no whitespace errors; branch changes are limited to the migration, tests, design, and plan.

### Task 7: Upgrade and verify the running local database

**Files:**
- Runtime only: `back/instance/dev.db` (gitignored).

- [ ] **Step 1: Upgrade to revision 019**

Run: `cd back && DB_URL=sqlite:///dev.db FLASK_APP=manage.py .venv/bin/flask db upgrade`

Expected: Alembic reports `Running upgrade 018 -> 019`.

- [ ] **Step 2: Verify seeded rows**

Run:

```bash
sqlite3 -header -column back/instance/dev.db \
  "SELECT code, name, status, version FROM units ORDER BY code;"
```

Expected: exactly the eight designed units, all `ENABLED` at version `1`.

- [ ] **Step 3: Revalidate the previous 22-row preview without persisting a job**

Run:

```bash
cd back && DB_URL=sqlite:///dev.db .venv/bin/python -c 'from manage import app; from app.extensions import db; from app.models import ImportJob; from app.services import import_service; app.app_context().push(); job=db.session.get(ImportJob, 3); assert job is not None; rows=[row["values"] for row in job.preview_data]; preview=import_service._master_preview("CATEGORY", rows); errors=[(row["line"], row["errors"]) for row in preview if row["errors"]]; print({"rows": len(preview), "errors": errors}); assert not errors'
```

Expected: `{'rows': 22, 'errors': []}`. The user can then re-upload the original file.

- [ ] **Step 4: Check health**

Run: `curl -fsS http://127.0.0.1:8081/health`

Expected: HTTP 200 with `"status":"UP"` and database `"ok":true`.
