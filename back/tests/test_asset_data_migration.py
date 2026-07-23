from __future__ import annotations

from datetime import date
import importlib.util
from io import StringIO
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from typing import Any

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite
from sqlalchemy.engine import Inspector

BACK_DIR = Path(__file__).resolve().parents[1]
MIGRATION = BACK_DIR / "migrations" / "versions" / "006_asset_data_foundation.py"

ForeignKeyColumns = tuple[str, ...]
ForeignKeyNameMap = dict[str, dict[ForeignKeyColumns, str]]
ForeignKeyContract = tuple[
    str | None,
    str,
    ForeignKeyColumns,
    ForeignKeyColumns,
    str | None,
]

PERMISSIONS = {
    "supplier:view": (
        "查看供应商",
        "supplier",
        {"SUPER_ADMIN", "ASSET_ADMIN", "USER"},
    ),
    "supplier:create": (
        "新增供应商",
        "supplier",
        {"SUPER_ADMIN", "ASSET_ADMIN"},
    ),
    "supplier:edit": (
        "编辑供应商",
        "supplier",
        {"SUPER_ADMIN", "ASSET_ADMIN"},
    ),
    "supplier:disable": (
        "停用恢复供应商",
        "supplier",
        {"SUPER_ADMIN", "ASSET_ADMIN"},
    ),
    "supplier:delete": ("删除供应商", "supplier", {"SUPER_ADMIN"}),
    "asset:data:complete": (
        "补充资产资料",
        "asset",
        {"SUPER_ADMIN", "ASSET_ADMIN"},
    ),
    "asset:service-life:update": (
        "调整资产使用期限",
        "asset",
        {"SUPER_ADMIN", "ASSET_ADMIN"},
    ),
}

ASSET_FOUNDATION_COLUMNS = {
    "unit_id",
    "supplier_id",
    "service_life_months",
    "expected_expiry_date",
    "source_id",
    "location_id",
    "custom_attributes",
    "data_completeness",
}
STOCK_IN_FOUNDATION_COLUMNS = {
    "supplier_id",
    "supplier_snapshot",
    "service_life_months",
    "expected_expiry_date",
    "custom_attributes",
}

NAMED_FOREIGN_KEYS: ForeignKeyNameMap = {
    "assets": {
        ("holder_user_id",): "fk_assets_holder_user_id",
        ("public_object_id",): "fk_assets_public_object_id",
        ("usage_department_id",): "fk_assets_usage_department_id",
        ("parent_asset_id",): "fk_assets_parent_asset_id",
        ("supplier_id",): "fk_assets_supplier_id",
    },
    "stock_in_items": {
        ("supplier_id",): "fk_stock_in_items_supplier_id",
    },
}

FROZEN_006_METADATA = sa.MetaData()
FROZEN_SUPPLIER_CODE_SEQUENCES = sa.Table(
    "supplier_code_sequences",
    FROZEN_006_METADATA,
    sa.Column("prefix", sa.String(length=16), primary_key=True, nullable=False),
    sa.Column("current_value", sa.Integer(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)
FROZEN_SUPPLIERS = sa.Table(
    "suppliers",
    FROZEN_006_METADATA,
    sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
    sa.Column("code", sa.String(length=64), nullable=False, unique=True, index=True),
    sa.Column("name", sa.String(length=255), nullable=False, unique=True, index=True),
    sa.Column(
        "unified_social_credit_code",
        sa.String(length=64),
        nullable=True,
        unique=True,
        index=True,
    ),
    sa.Column("contact_name", sa.String(length=128), nullable=True),
    sa.Column("contact_phone", sa.String(length=64), nullable=True),
    sa.Column("address", sa.String(length=500), nullable=True),
    sa.Column("remark", sa.String(length=1000), nullable=True),
    sa.Column("status", sa.String(length=16), nullable=False, index=True),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)
FROZEN_ASSETS = sa.Table(
    "assets",
    FROZEN_006_METADATA,
    sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
    sa.Column(
        "asset_code", sa.String(length=191), nullable=False, unique=True, index=True
    ),
    sa.Column("asset_name", sa.String(length=255), nullable=False, index=True),
    sa.Column("status", sa.String(length=32), nullable=False, index=True),
    sa.Column(
        "organization_id",
        sa.Integer(),
        sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    ),
    sa.Column("usage_type", sa.String(length=16), nullable=True, index=True),
    sa.Column(
        "holder_user_id",
        sa.Integer(),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    ),
    sa.Column(
        "public_object_id",
        sa.Integer(),
        sa.ForeignKey("public_usage_objects.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    ),
    sa.Column(
        "usage_department_id",
        sa.Integer(),
        sa.ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    ),
    sa.Column(
        "parent_asset_id",
        sa.Integer(),
        sa.ForeignKey("assets.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    ),
    sa.Column(
        "category_id",
        sa.Integer(),
        sa.ForeignKey("asset_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    ),
    sa.Column(
        "unit_id",
        sa.Integer(),
        sa.ForeignKey("units.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    ),
    sa.Column(
        "supplier_id",
        sa.Integer(),
        sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    ),
    sa.Column("original_amount", sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column("zero_amount_reason", sa.String(length=255), nullable=True),
    sa.Column("purchase_date", sa.Date(), nullable=False),
    sa.Column("service_life_months", sa.Integer(), nullable=False),
    sa.Column("expected_expiry_date", sa.Date(), nullable=False),
    sa.Column(
        "manager_id",
        sa.Integer(),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    ),
    sa.Column(
        "source_id",
        sa.Integer(),
        sa.ForeignKey("asset_sources.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    ),
    sa.Column(
        "location_id",
        sa.Integer(),
        sa.ForeignKey("asset_locations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    ),
    sa.Column("specification_model", sa.String(length=255), nullable=True),
    sa.Column("serial_number", sa.String(length=191), nullable=True),
    sa.Column(
        "normalized_serial",
        sa.String(length=191),
        nullable=True,
        unique=True,
        index=True,
    ),
    sa.Column("receipt_no", sa.String(length=128), nullable=True),
    sa.Column("remark", sa.Text(), nullable=True),
    sa.Column("custom_attributes", sa.JSON(), nullable=False),
    sa.Column("data_completeness", sa.String(length=16), nullable=False, index=True),
    sa.Column(
        "created_from_request_id",
        sa.Integer(),
        sa.ForeignKey("operation_requests.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    ),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)
FROZEN_STOCK_IN_ITEMS = sa.Table(
    "stock_in_items",
    FROZEN_006_METADATA,
    sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
    sa.Column(
        "stock_in_request_id",
        sa.Integer(),
        sa.ForeignKey("stock_in_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    sa.Column(
        "asset_code", sa.String(length=191), nullable=False, unique=True, index=True
    ),
    sa.Column("asset_name", sa.String(length=255), nullable=False),
    sa.Column(
        "category_id",
        sa.Integer(),
        sa.ForeignKey("asset_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    ),
    sa.Column(
        "unit_id",
        sa.Integer(),
        sa.ForeignKey("units.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    ),
    sa.Column(
        "supplier_id",
        sa.Integer(),
        sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    ),
    sa.Column("supplier_snapshot", sa.JSON(), nullable=True),
    sa.Column("original_amount", sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column("zero_amount_reason", sa.String(length=255), nullable=True),
    sa.Column("purchase_date", sa.Date(), nullable=False),
    sa.Column("service_life_months", sa.Integer(), nullable=False),
    sa.Column("expected_expiry_date", sa.Date(), nullable=False),
    sa.Column(
        "manager_id",
        sa.Integer(),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    ),
    sa.Column(
        "source_id",
        sa.Integer(),
        sa.ForeignKey("asset_sources.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    ),
    sa.Column(
        "location_id",
        sa.Integer(),
        sa.ForeignKey("asset_locations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    ),
    sa.Column("specification_model", sa.String(length=255), nullable=True),
    sa.Column("serial_number", sa.String(length=191), nullable=True),
    sa.Column("normalized_serial", sa.String(length=191), nullable=True, index=True),
    sa.Column(
        "serial_reservation_key",
        sa.String(length=191),
        nullable=True,
        unique=True,
        index=True,
    ),
    sa.Column("receipt_no", sa.String(length=128), nullable=True),
    sa.Column("remark", sa.Text(), nullable=True),
    sa.Column("custom_attributes", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)


def _load_migration(module_name: str = "migration_006") -> Any:
    assert MIGRATION.is_file()
    spec = importlib.util.spec_from_file_location(module_name, MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _migration_env(tmp_path: Path, database: Path) -> dict[str, str]:
    empty_env_file = tmp_path / "empty.env"
    empty_env_file.write_text("", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "FLASK_APP": "manage.py",
            "FLASK_ENV": "dev",
            "ENV_FILE": str(empty_env_file),
            "DB_URL": f"sqlite:///{database}",
            "LOG_FILE_ENABLED": "false",
            "REDIS_HOST": "",
        }
    )
    return env


def _run_db(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(BACK_DIR / ".venv" / "bin" / "python"), "-m", "flask", "db", *args],
        cwd=BACK_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _upgrade_to_005_and_seed(tmp_path: Path, database: Path) -> dict[str, str]:
    env = _migration_env(tmp_path, database)
    upgrade = _run_db(env, "upgrade", "005")
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr

    timestamp = "2026-07-23 00:00:00"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO organizations "
            "(id, code, name, status, version, created_at, updated_at) "
            "VALUES (101, 'MIG-ORG', 'Migration Org', 'ENABLED', 1, ?, ?)",
            (timestamp, timestamp),
        )
        connection.execute(
            "INSERT INTO units "
            "(id, code, name, status, version, created_at, updated_at) "
            "VALUES (101, 'MIG-UNIT', 'Migration Unit', 'ENABLED', 1, ?, ?)",
            (timestamp, timestamp),
        )
        connection.execute(
            "INSERT INTO asset_sources "
            "(id, code, name, status, version, created_at, updated_at) "
            "VALUES (101, 'MIG-SOURCE', 'Migration Source', 'ENABLED', 1, ?, ?)",
            (timestamp, timestamp),
        )
        connection.execute(
            "INSERT INTO asset_locations "
            "(id, code, name, status, is_selectable, version, created_at, updated_at) "
            "VALUES (101, 'MIG-LOCATION', 'Migration Location', 'ENABLED', 1, 1, ?, ?)",
            (timestamp, timestamp),
        )
        connection.executemany(
            "INSERT INTO asset_categories "
            "(id, code, name, service_life_months, default_unit_id, status, "
            "version, created_at, updated_at) VALUES (?, ?, ?, ?, 101, "
            "'ENABLED', 1, ?, ?)",
            [
                (101, "MIG-CAT-ASSET", "Migration Asset", 12, timestamp, timestamp),
                (102, "MIG-CAT-STOCK", "Migration Stock", 1, timestamp, timestamp),
            ],
        )
        connection.execute(
            "INSERT INTO assets "
            "(id, asset_code, asset_name, status, organization_id, category_id, "
            "unit_id, original_amount, purchase_date, manager_id, source_id, "
            "location_id, version, created_at, updated_at) VALUES "
            "(101, 'MIG-ASSET-001', 'Legacy Asset', 'IDLE', 101, 101, 101, "
            "100.00, '2024-02-29', 1, 101, 101, 1, ?, ?)",
            (timestamp, timestamp),
        )
        connection.execute(
            "INSERT INTO operation_requests "
            "(id, request_no, operation_type, applicant_id, approval_channel, "
            "approval_execution_mode, approval_status, execution_status, "
            "flow_version, version, created_at, updated_at) VALUES "
            "(101, 'MIG-STOCK-IN-001', 'STOCK_IN', 1, 'INTERNAL', "
            "'AUTO_ON_APPROVAL', 'PENDING', 'NOT_STARTED', 1, 1, ?, ?)",
            (timestamp, timestamp),
        )
        connection.execute(
            "INSERT INTO stock_in_requests "
            "(id, operation_request_id, organization_id, created_at, updated_at) "
            "VALUES (101, 101, 101, ?, ?)",
            (timestamp, timestamp),
        )
        connection.execute(
            "INSERT INTO stock_in_items "
            "(id, stock_in_request_id, asset_code, asset_name, category_id, "
            "unit_id, original_amount, purchase_date, manager_id, source_id, "
            "location_id, created_at, updated_at) VALUES "
            "(101, 101, 'MIG-STOCK-001', 'Pending Stock Item', 102, 101, "
            "200.00, '2026-01-31', 1, 101, 101, ?, ?)",
            (timestamp, timestamp),
        )
        connection.commit()
    return env


def _columns(
    connection: sqlite3.Connection, table_name: str
) -> dict[str, tuple[str, bool]]:
    return {
        row[1]: (row[2].upper(), bool(row[3]))
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def _indexes(
    connection: sqlite3.Connection, table_name: str
) -> dict[str, tuple[bool, tuple[str, ...]]]:
    indexes: dict[str, tuple[bool, tuple[str, ...]]] = {}
    for row in connection.execute(f"PRAGMA index_list({table_name})").fetchall():
        name = row[1]
        if name.startswith("sqlite_autoindex_"):
            continue
        columns = tuple(
            item[2]
            for item in connection.execute(f'PRAGMA index_info("{name}")').fetchall()
        )
        indexes[name] = (bool(row[2]), columns)
    return indexes


def _foreign_keys(
    connection: sqlite3.Connection, table_name: str
) -> set[tuple[str, str, str, str]]:
    return {
        (row[2], row[3], row[4], row[6])
        for row in connection.execute(
            f"PRAGMA foreign_key_list({table_name})"
        ).fetchall()
    }


def _metadata_columns(metadata_table: sa.Table) -> dict[str, tuple[str, bool]]:
    return {
        column.name: (
            str(column.type.compile(dialect=sqlite.dialect())).upper(),
            not column.nullable,
        )
        for column in metadata_table.c
    }


def _metadata_indexes(
    metadata_table: sa.Table,
) -> dict[str, tuple[bool, tuple[str, ...]]]:
    indexes: dict[str, tuple[bool, tuple[str, ...]]] = {}
    for index in metadata_table.indexes:
        assert index.name is not None
        indexes[index.name] = (
            bool(index.unique),
            tuple(column.name for column in index.columns),
        )
    return indexes


def _metadata_foreign_keys(
    metadata_table: sa.Table,
) -> set[ForeignKeyContract]:
    expected: set[ForeignKeyContract] = set()
    named_constraints = NAMED_FOREIGN_KEYS.get(metadata_table.name, {})
    for constraint in metadata_table.foreign_key_constraints:
        source_columns = tuple(constraint.column_keys)
        target_pairs = [
            element.target_fullname.rsplit(".", maxsplit=1)
            for element in constraint.elements
        ]
        target_tables = {target_table for target_table, _column in target_pairs}
        assert len(target_tables) == 1
        constraint_name = (
            constraint.name
            if isinstance(constraint.name, str)
            else named_constraints.get(source_columns)
        )
        expected.add(
            (
                constraint_name,
                target_tables.pop(),
                source_columns,
                tuple(column for _target_table, column in target_pairs),
                constraint.ondelete,
            )
        )
    return expected


def _inspected_foreign_keys(
    inspector: Inspector, table_name: str
) -> set[ForeignKeyContract]:
    return {
        (
            foreign_key["name"],
            foreign_key["referred_table"],
            tuple(foreign_key["constrained_columns"]),
            tuple(foreign_key["referred_columns"]),
            foreign_key["options"].get("ondelete"),
        )
        for foreign_key in inspector.get_foreign_keys(table_name)
    }


def _assert_table_matches_metadata(
    connection: sqlite3.Connection,
    inspector: Inspector,
    table_name: str,
    metadata_table: sa.Table,
) -> None:
    assert _columns(connection, table_name) == _metadata_columns(metadata_table)
    assert _indexes(connection, table_name) == _metadata_indexes(metadata_table)
    assert _inspected_foreign_keys(inspector, table_name) == _metadata_foreign_keys(
        metadata_table
    )


def _permission_state(
    connection: sqlite3.Connection,
) -> tuple[dict[str, tuple[str, str, int]], dict[str, set[str]]]:
    codes = tuple(PERMISSIONS)
    placeholders = ",".join("?" for _ in codes)
    permission_rows = connection.execute(
        "SELECT code, name, module, enabled FROM permissions "
        f"WHERE code IN ({placeholders}) ORDER BY code",
        codes,
    ).fetchall()
    role_rows = connection.execute(
        "SELECT p.code, r.code FROM permissions p "
        "JOIN role_permissions rp ON rp.permission_id = p.id "
        "JOIN roles r ON r.id = rp.role_id "
        f"WHERE p.code IN ({placeholders}) ORDER BY p.code, r.code",
        codes,
    ).fetchall()
    permissions = {
        code: (name, module, enabled) for code, name, module, enabled in permission_rows
    }
    roles: dict[str, set[str]] = {code: set() for code in permissions}
    for permission_code, role_code in role_rows:
        roles[permission_code].add(role_code)
    return permissions, roles


def _foundation_snapshot(database: Path) -> dict[str, object]:
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        return {
            "version": connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone(),
            "supplier_tables": {
                table
                for table in tables
                if table in {"supplier_code_sequences", "suppliers"}
            },
            "supplier_sequence_columns": _columns(
                connection, "supplier_code_sequences"
            ),
            "supplier_columns": _columns(connection, "suppliers"),
            "supplier_indexes": _indexes(connection, "suppliers"),
            "asset_columns": _columns(connection, "assets"),
            "asset_indexes": _indexes(connection, "assets"),
            "asset_foreign_keys": _foreign_keys(connection, "assets"),
            "stock_columns": _columns(connection, "stock_in_items"),
            "stock_indexes": _indexes(connection, "stock_in_items"),
            "stock_foreign_keys": _foreign_keys(connection, "stock_in_items"),
            "permissions": _permission_state(connection),
            "sequence": connection.execute(
                "SELECT prefix, current_value FROM supplier_code_sequences"
            ).fetchall(),
            "supplier_rows": connection.execute(
                "SELECT * FROM suppliers ORDER BY id"
            ).fetchall(),
            "asset_rows": connection.execute(
                "SELECT * FROM assets ORDER BY id"
            ).fetchall(),
            "stock_rows": connection.execute(
                "SELECT * FROM stock_in_items ORDER BY id"
            ).fetchall(),
        }


def test_asset_data_foundation_migration_exists_and_uses_ordered_phases(
    monkeypatch,
) -> None:
    module = _load_migration()
    assert module.revision == "006"
    assert module.down_revision == "005"

    calls: list[str] = []
    phases = (
        "_create_supplier_tables",
        "_add_nullable_asset_columns",
        "_add_nullable_stock_in_columns",
        "_backfill_existing_rows",
        "_enforce_final_nullability",
        "_seed_permissions",
    )
    for phase in phases:
        monkeypatch.setattr(
            module,
            phase,
            lambda phase_name=phase: calls.append(phase_name),
        )
    module.upgrade()
    assert calls == list(phases)


@pytest.mark.parametrize(
    ("purchase_date", "service_life_months", "expected"),
    [
        ("2024-02-29", 12, "2025-02-28"),
        ("2026-01-31", 1, "2026-02-28"),
        ("2024-01-31", 1, "2024-02-29"),
    ],
)
def test_migration_expiry_backfill_clamps_end_of_month(
    purchase_date: str, service_life_months: int, expected: str
) -> None:
    module = _load_migration("migration_006_expiry")
    assert (
        module._calculate_expected_expiry(
            module.date.fromisoformat(purchase_date), service_life_months
        ).isoformat()
        == expected
    )


def test_backfill_uses_keyset_pages_and_typed_executemany(monkeypatch) -> None:
    module = _load_migration("migration_006_batched_backfill")
    monkeypatch.setattr(module, "_BACKFILL_BATCH_SIZE", 2)

    metadata = sa.MetaData()
    categories = sa.Table(
        "asset_categories",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_life_months", sa.Integer(), nullable=False),
    )
    assets = sa.Table(
        "assets",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("service_life_months", sa.Integer(), nullable=True),
        sa.Column("expected_expiry_date", sa.Date(), nullable=True),
        sa.Column("custom_attributes", sa.JSON(), nullable=True),
        sa.Column("data_completeness", sa.String(length=16), nullable=True),
    )
    stock_in_items = sa.Table(
        "stock_in_items",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("service_life_months", sa.Integer(), nullable=True),
        sa.Column("expected_expiry_date", sa.Date(), nullable=True),
        sa.Column("custom_attributes", sa.JSON(), nullable=True),
    )
    engine = sa.create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    update_batches: list[tuple[str, bool, int]] = []
    page_selects: list[str] = []

    def record_execution(*args: Any) -> None:
        statement = " ".join(str(args[2]).lower().split())
        execution_context = args[4]
        executemany = bool(args[5])
        if statement.startswith("update assets "):
            update_batches.append(
                ("assets", executemany, len(execution_context.compiled_parameters))
            )
        elif statement.startswith("update stock_in_items "):
            update_batches.append(
                (
                    "stock_in_items",
                    executemany,
                    len(execution_context.compiled_parameters),
                )
            )
        elif statement.startswith("select") and (
            " from assets join asset_categories " in statement
            or " from stock_in_items join asset_categories " in statement
        ):
            page_selects.append(statement)

    sa.event.listen(engine, "before_cursor_execute", record_execution)
    ids = (1, 5, 9, 20)
    with engine.begin() as connection:
        connection.execute(
            sa.insert(categories),
            [{"id": 1, "service_life_months": 1}],
        )
        connection.execute(
            sa.insert(assets),
            [
                {
                    "id": row_id,
                    "category_id": 1,
                    "purchase_date": date(2026, 1, 31),
                }
                for row_id in ids
            ],
        )
        connection.execute(
            sa.insert(stock_in_items),
            [
                {
                    "id": row_id,
                    "category_id": 1,
                    "purchase_date": date(2026, 1, 31),
                }
                for row_id in ids
            ],
        )
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            module._backfill_existing_rows()

        assert (
            connection.execute(
                sa.select(
                    assets.c.service_life_months,
                    assets.c.expected_expiry_date,
                    assets.c.custom_attributes,
                    assets.c.data_completeness,
                ).order_by(assets.c.id)
            ).all()
            == [(1, date(2026, 2, 28), {}, "COMPLETE")] * 4
        )
        assert (
            connection.execute(
                sa.select(
                    stock_in_items.c.service_life_months,
                    stock_in_items.c.expected_expiry_date,
                    stock_in_items.c.custom_attributes,
                ).order_by(stock_in_items.c.id)
            ).all()
            == [(1, date(2026, 2, 28), {})] * 4
        )

    assert update_batches == [
        ("assets", True, 2),
        ("assets", True, 2),
        ("stock_in_items", True, 2),
        ("stock_in_items", True, 2),
    ]
    assert len(page_selects) == 6
    keyset_selects = [statement for statement in page_selects if " where " in statement]
    assert len(keyset_selects) == 4
    assert all(".id >" in statement for statement in keyset_selects)
    assert all(" order by " in statement for statement in page_selects)
    assert all(" limit " in statement for statement in page_selects)
    engine.dispose()


def test_asset_data_migration_round_trip_schema_backfill_and_permissions(
    tmp_path: Path,
) -> None:
    database = tmp_path / "asset-data-round-trip.db"
    env = _upgrade_to_005_and_seed(tmp_path, database)

    upgrade = _run_db(env, "upgrade", "006")
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr

    engine = sa.create_engine(f"sqlite:///{database}")
    inspector = sa.inspect(engine)
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {"supplier_code_sequences", "suppliers"} <= tables
        assert connection.execute(
            "SELECT prefix, current_value FROM supplier_code_sequences"
        ).fetchall() == [("SUP", 0)]

        _assert_table_matches_metadata(
            connection,
            inspector,
            "supplier_code_sequences",
            FROZEN_SUPPLIER_CODE_SEQUENCES,
        )
        _assert_table_matches_metadata(
            connection,
            inspector,
            "suppliers",
            FROZEN_SUPPLIERS,
        )
        _assert_table_matches_metadata(
            connection,
            inspector,
            "assets",
            FROZEN_ASSETS,
        )
        _assert_table_matches_metadata(
            connection,
            inspector,
            "stock_in_items",
            FROZEN_STOCK_IN_ITEMS,
        )

        asset = connection.execute(
            "SELECT service_life_months, expected_expiry_date, custom_attributes, "
            "data_completeness, supplier_id FROM assets WHERE id = 101"
        ).fetchone()
        stock_item = connection.execute(
            "SELECT service_life_months, expected_expiry_date, custom_attributes, "
            "supplier_id, supplier_snapshot FROM stock_in_items WHERE id = 101"
        ).fetchone()
        assert asset[:2] == (12, "2025-02-28")
        assert json.loads(asset[2]) == {}
        assert asset[3:] == ("COMPLETE", None)
        assert stock_item[:2] == (1, "2026-02-28")
        assert json.loads(stock_item[2]) == {}
        assert stock_item[3:] == (None, None)

        actual_permissions, actual_roles = _permission_state(connection)
        assert actual_permissions == {
            code: (name, module, 1)
            for code, (name, module, _roles) in PERMISSIONS.items()
        }
        assert actual_roles == {
            code: roles for code, (_name, _module, roles) in PERMISSIONS.items()
        }
    engine.dispose()

    downgrade = _run_db(env, "downgrade", "005")
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert "supplier_code_sequences" not in tables
        assert "suppliers" not in tables
        assert "asset_code_reservations" in tables
        assert not (
            ASSET_FOUNDATION_COLUMNS - {"unit_id", "source_id", "location_id"}
        ) & set(_columns(connection, "assets"))
        assert not STOCK_IN_FOUNDATION_COLUMNS & set(
            _columns(connection, "stock_in_items")
        )
        for column_name in ("unit_id", "source_id", "location_id"):
            assert _columns(connection, "assets")[column_name][1] is True
        assert "ix_assets_supplier_id" not in _indexes(connection, "assets")
        assert "ix_assets_data_completeness" not in _indexes(connection, "assets")
        assert "ix_stock_in_items_supplier_id" not in _indexes(
            connection, "stock_in_items"
        )
        assert not any(
            target == "suppliers"
            for target, _source, _remote, _ondelete in (
                _foreign_keys(connection, "assets")
                | _foreign_keys(connection, "stock_in_items")
            )
        )
        assert _permission_state(connection) == ({}, {})
        assert connection.execute(
            "SELECT asset_code FROM assets WHERE id = 101"
        ).fetchone() == ("MIG-ASSET-001",)
        assert connection.execute(
            "SELECT asset_code FROM stock_in_items WHERE id = 101"
        ).fetchone() == ("MIG-STOCK-001",)

    reupgrade = _run_db(env, "upgrade", "006")
    assert reupgrade.returncode == 0, reupgrade.stdout + reupgrade.stderr
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT prefix, current_value FROM supplier_code_sequences"
        ).fetchall() == [("SUP", 0)]
        assert connection.execute(
            "SELECT COUNT(*) FROM permissions WHERE code IN "
            f"({','.join('?' for _ in PERMISSIONS)})",
            tuple(PERMISSIONS),
        ).fetchone() == (7,)
        assert connection.execute(
            "SELECT service_life_months, expected_expiry_date, data_completeness "
            "FROM assets WHERE id = 101"
        ).fetchone() == (12, "2025-02-28", "COMPLETE")


@pytest.mark.parametrize("nullable_column", ["unit_id", "source_id", "location_id"])
def test_downgrade_preflight_rejects_incomplete_assets_before_mutation(
    tmp_path: Path, nullable_column: str
) -> None:
    database = tmp_path / f"asset-data-guard-{nullable_column}.db"
    env = _upgrade_to_005_and_seed(tmp_path, database)
    upgrade = _run_db(env, "upgrade", "006")
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr

    with sqlite3.connect(database) as connection:
        connection.execute(f"UPDATE assets SET {nullable_column} = NULL WHERE id = 101")
        connection.commit()
    before = _foundation_snapshot(database)

    downgrade = _run_db(env, "downgrade", "005")
    output = downgrade.stdout + downgrade.stderr
    assert downgrade.returncode != 0
    for column_name in ("unit_id", "source_id", "location_id"):
        assert column_name in output
    assert _foundation_snapshot(database) == before

    module = _load_migration(f"migration_006_guard_{nullable_column}")
    engine = sa.create_engine(f"sqlite:///{database}")
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context), pytest.raises(RuntimeError):
            module._preflight_downgrade()
    engine.dispose()


def test_asset_data_migration_ddl_compiles_for_mysql(monkeypatch) -> None:
    module = _load_migration("migration_006_mysql")
    monkeypatch.setattr(module, "_backfill_existing_rows", lambda: None)
    monkeypatch.setattr(module, "_seed_permissions", lambda: None)

    upgrade_output = StringIO()
    upgrade_context = MigrationContext.configure(
        dialect_name="mysql",
        opts={
            "as_sql": True,
            "literal_binds": True,
            "output_buffer": upgrade_output,
        },
    )
    with Operations.context(upgrade_context):
        module.upgrade()

    upgrade_sql = upgrade_output.getvalue()
    assert "CREATE TABLE supplier_code_sequences" in upgrade_sql
    assert "CREATE TABLE suppliers" in upgrade_sql
    assert "supplier_snapshot JSON" in upgrade_sql
    assert upgrade_sql.count("ADD COLUMN custom_attributes JSON") == 2
    assert "CONSTRAINT fk_assets_supplier_id" in upgrade_sql
    assert "CONSTRAINT fk_stock_in_items_supplier_id" in upgrade_sql
    assert "ON DELETE RESTRICT" in upgrade_sql
    for index_name in (
        "ix_suppliers_code",
        "ix_suppliers_name",
        "ix_suppliers_unified_social_credit_code",
        "ix_suppliers_status",
        "ix_assets_supplier_id",
        "ix_assets_data_completeness",
        "ix_stock_in_items_supplier_id",
    ):
        assert index_name in upgrade_sql
    for column_name in ("unit_id", "source_id", "location_id"):
        assert f"MODIFY {column_name} INTEGER NULL" in upgrade_sql
    assert "MODIFY service_life_months INTEGER NOT NULL" in upgrade_sql
    assert "MODIFY expected_expiry_date DATE NOT NULL" in upgrade_sql
    assert "MODIFY custom_attributes JSON NOT NULL" in upgrade_sql
    assert "custom_attributes JSON DEFAULT" not in upgrade_sql
    assert "expected_expiry_date DATE DEFAULT" not in upgrade_sql

    def emit_preflight_marker() -> None:
        module.op.execute(sa.text("SELECT 1 AS preflight_marker"))

    def emit_permission_markers() -> None:
        module.op.execute(sa.text("DELETE FROM role_permissions WHERE 1 = 0"))
        module.op.execute(sa.text("DELETE FROM permissions WHERE 1 = 0"))

    monkeypatch.setattr(module, "_preflight_downgrade", emit_preflight_marker)
    monkeypatch.setattr(module, "_delete_permissions", emit_permission_markers)
    downgrade_output = StringIO()
    downgrade_context = MigrationContext.configure(
        dialect_name="mysql",
        opts={
            "as_sql": True,
            "literal_binds": True,
            "output_buffer": downgrade_output,
        },
    )
    with Operations.context(downgrade_context):
        module.downgrade()

    downgrade_sql = downgrade_output.getvalue()
    assert downgrade_sql.index("SELECT 1 AS preflight_marker") < downgrade_sql.index(
        "ALTER TABLE stock_in_items"
    )
    assert downgrade_sql.index("DROP FOREIGN KEY fk_assets_supplier_id") < (
        downgrade_sql.index("DROP INDEX ix_assets_supplier_id")
    )
    assert downgrade_sql.index("DROP FOREIGN KEY fk_stock_in_items_supplier_id") < (
        downgrade_sql.index("DROP INDEX ix_stock_in_items_supplier_id")
    )
    asset_index_drop = downgrade_sql.index("DROP INDEX ix_assets_supplier_id")
    stock_index_drop = downgrade_sql.index("DROP INDEX ix_stock_in_items_supplier_id")
    assert asset_index_drop < downgrade_sql.index(
        "DROP COLUMN supplier_id", asset_index_drop
    )
    assert stock_index_drop < downgrade_sql.index(
        "DROP COLUMN supplier_id", stock_index_drop
    )
    for column_name in ("unit_id", "source_id", "location_id"):
        assert f"MODIFY {column_name} INTEGER NOT NULL" in downgrade_sql
    assert downgrade_sql.index("DROP TABLE suppliers") < downgrade_sql.index(
        "DROP TABLE supplier_code_sequences"
    )
    assert downgrade_sql.index("DROP TABLE supplier_code_sequences") < (
        downgrade_sql.index("DELETE FROM role_permissions")
    )
    assert downgrade_sql.index("DELETE FROM role_permissions") < (
        downgrade_sql.index("DELETE FROM permissions")
    )
    assert "asset_code_reservations" not in downgrade_sql
