# Asset Data Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver supplier master data, import-compatible asset fields, immutable service-life snapshots, reusable asset scope rules, and safe single/batch completion of missing asset data on Alembic revision 006.

**Architecture:** Supplier is a standalone aggregate with its own persistent code sequence and API. Asset visibility is centralized in a narrow access service; pure date/completeness calculations remain separate from mutating completion use cases. Completion uses a dedicated null-only CAS and the existing lifecycle/audit stores, while normal stock-in freezes service-life and supplier data at submission time.

**Tech Stack:** Flask 3, Python 3.13, SQLAlchemy 2, Marshmallow 3, Alembic, SQLite, MySQL 8 dialect validation, pytest, Ruff, mypy.

All `git add`, convention-guard, and `git commit` commands in this plan run from the repository root. The convention guard scans staged files only, so every commit stages its exact file set before invoking `scripts/guard-conventions.sh`.

---

## Locked boundaries

- Keep the dependency direction `api -> services -> repositories -> models -> db`.
- Business routes use GET and POST only.
- `unit_id`, `source_id`, and `location_id` become nullable only on `Asset`; normal `StockInItem` and the stock-in request schema remain strict.
- `Asset.service_life_months`, `Asset.expected_expiry_date`, `StockInItem.service_life_months`, and `StockInItem.expected_expiry_date` are non-null.
- Revision 006 does not add an `asset_import_item_id` FK to `AssetCodeReservation`; that XOR relationship belongs to the later import migration. It only narrows the current allocation entry point to `reserve_for_stock_in()`.
- A data-completion request never creates an `OperationRequest`, but it refuses assets with an active `AssetBusinessLock`.
- Completion can only change a selected field from SQL NULL to an enabled standard-data ID. It cannot overwrite a value.
- `operation_service.create_request()` rejects every `INCOMPLETE` Asset before creating a usage or return request, even when the request supplies a non-null target location. Operation execution never doubles as data completion and therefore cannot bypass completion lifecycle/audit records.
- SELF asset scope is `manager_id == actor_id OR holder_user_id == actor_id`.
- Supplier permissions are exactly `supplier:view/create/edit/disable/delete`.
- Explicitly overriding a category's stock-in service life requires `asset:service-life:update`; omission still uses the category default.
- Revision 006 does not seed `asset:amount:update`; that permission is introduced with the later asset-edit/batch-update feature.
- Revision 006 can expose which standard fields are missing, but the original unmatched Excel text remains a later import-detail responsibility because no ImportItem exists yet.
- Shared exports, Blueprint registration, permissions, migration 006, and audit-kernel integration are owned by the primary agent.

## File map

Create:

- `back/app/models/supplier.py`
- `back/app/repositories/supplier_repository.py`
- `back/app/services/supplier_service.py`
- `back/app/services/asset_access_service.py`
- `back/app/services/asset_data_service.py`
- `back/app/services/asset_data_completion_service.py`
- `back/app/schemas/supplier.py`
- `back/app/api/suppliers.py`
- `back/tests/test_supplier_models.py`
- `back/tests/test_suppliers.py`
- `back/tests/test_asset_data_foundation.py`
- `back/tests/test_asset_data_completion.py`
- `back/tests/test_asset_data_migration.py`
- `back/migrations/versions/006_asset_data_foundation.py`

Modify:

- `back/app/enums/__init__.py`
- `back/app/models/asset.py`
- `back/app/models/workflow.py`
- `back/app/models/__init__.py`
- `back/app/repositories/asset_repository.py`
- `back/app/repositories/workflow_repository.py`
- `back/app/repositories/__init__.py`
- `back/app/services/asset_service.py`
- `back/app/services/operation_service.py`
- `back/app/services/stock_in_service.py`
- `back/app/services/audit_service.py`
- `back/app/services/__init__.py`
- `back/app/schemas/asset.py`
- `back/app/schemas/stock_in.py`
- `back/app/schemas/__init__.py`
- `back/app/api/assets.py`
- `back/app/api/__init__.py`
- `back/tests/test_asset_usage_service.py`
- `back/tests/test_stock_in_foundation_compat.py`
- focused existing stock-in, asset, and migration tests when their assertions need the new non-null fields.

## Task 1: Persist supplier and immutable asset-data fields

**Files:**

- Create: `back/app/models/supplier.py`
- Create: `back/app/services/asset_data_service.py`
- Create: `back/tests/test_supplier_models.py`
- Create: `back/tests/test_asset_data_foundation.py`
- Modify: `back/app/enums/__init__.py`
- Modify: `back/app/models/asset.py`
- Modify: `back/app/models/workflow.py`
- Modify: `back/app/models/__init__.py`
- Modify: `back/app/services/asset_service.py`
- Modify: `back/app/services/operation_service.py`
- Modify: `back/app/services/asset_usage_service.py`
- Modify: `back/app/services/stock_in_service.py`
- Modify: `back/app/services/__init__.py`
- Modify: `back/tests/test_asset_usage_service.py`
- Modify: `back/tests/test_stock_in_foundation_compat.py`
- Modify: the eleven direct-constructor test files enumerated in the commit step.

- [ ] **Step 1: Write the failing model contracts**

```python
# back/tests/test_supplier_models.py
from app.models import Supplier, SupplierCodeSequence


def test_supplier_contract_uses_independent_persistent_sequence(app) -> None:
    assert SupplierCodeSequence.__table__.primary_key.columns.keys() == ["prefix"]
    assert SupplierCodeSequence.__table__.c.current_value.nullable is False
    assert Supplier.__table__.c.code.unique is True
    assert Supplier.__table__.c.name.unique is True
    assert Supplier.__table__.c.unified_social_credit_code.unique is True
```

```python
# back/tests/test_asset_data_foundation.py
from app.enums import AssetDataCompleteness
from app.models import Asset, StockInItem


def test_asset_data_contract_is_import_compatible_and_life_is_required(app) -> None:
    assert {item.value for item in AssetDataCompleteness} == {
        "COMPLETE",
        "INCOMPLETE",
    }
    for name in ("unit_id", "source_id", "location_id"):
        assert Asset.__table__.c[name].nullable is True
        assert StockInItem.__table__.c[name].nullable is False
    for table in (Asset.__table__, StockInItem.__table__):
        assert table.c.service_life_months.nullable is False
        assert table.c.expected_expiry_date.nullable is False
        assert table.c.custom_attributes.nullable is False
    assert Asset.__table__.c.data_completeness.nullable is False
```

- [ ] **Step 2: Run RED and verify the failure is the missing contract**

Run:

```bash
cd back
.venv/bin/python -m pytest tests/test_supplier_models.py tests/test_asset_data_foundation.py -q
```

Expected: collection fails because `Supplier`, `SupplierCodeSequence`, and `AssetDataCompleteness` do not exist.

- [ ] **Step 3: Add the enum and standalone supplier models**

```python
# back/app/enums/__init__.py
class AssetDataCompleteness(StringEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
```

```python
# back/app/models/supplier.py
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import RecordStatus
from app.extensions import db
from app.models.mixins import TimestampMixin


class SupplierCodeSequence(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "supplier_code_sequences"

    prefix: Mapped[str] = mapped_column(String(16), primary_key=True)
    current_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Supplier(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    unified_social_credit_code: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    contact_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    remark: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RecordStatus.ENABLED.value, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


__all__ = ["Supplier", "SupplierCodeSequence"]
```

- [ ] **Step 4: Add the Asset and StockInItem fields**

```python
# Add to Asset in back/app/models/asset.py
supplier_id: Mapped[int | None] = mapped_column(
    ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=True, index=True
)
service_life_months: Mapped[int] = mapped_column(Integer, nullable=False)
expected_expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
custom_attributes: Mapped[dict[str, Any]] = mapped_column(
    JSON, nullable=False, default=dict
)
data_completeness: Mapped[str] = mapped_column(
    String(16),
    nullable=False,
    default=AssetDataCompleteness.COMPLETE.value,
    index=True,
)
```

Change only the Asset annotations and nullability for `unit_id`, `source_id`, and `location_id` to `Mapped[int | None]` and `nullable=True`.

```python
# Add to StockInItem in back/app/models/workflow.py
supplier_id: Mapped[int | None] = mapped_column(
    ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=True, index=True
)
supplier_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
service_life_months: Mapped[int] = mapped_column(Integer, nullable=False)
expected_expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
custom_attributes: Mapped[dict[str, Any]] = mapped_column(
    JSON, nullable=False, default=dict
)
```

Import `Any` and `JSON` in the owning model files, and explicitly export the new enum and models from `app.enums` and `app.models`.

- [ ] **Step 5: Keep stock-in snapshots immutable and reject incomplete operation assets**

Move the pure end-of-month `calculate_expected_expiry` function into `asset_data_service.py` now so no temporary calculation is duplicated. Existing stock-in submission freezes the selected category's default `service_life_months`, calculated expiry, and `{}` custom attributes into each `StockInItem`. Existing formal execution copies only those frozen item values into `Asset` and sets `data_completeness=COMPLETE`; it does not re-read the category. Supplier remains `None` until Task 7 adds request support.

Make the common operation boundary fail closed: in `operation_service._validate_assets_and_targets`, reject an Asset when `data_completeness != COMPLETE` or any of `unit_id/source_id/location_id` is `None`. This check runs for both usage and return request creation before an `OperationRequest`, snapshot, or business lock is written. Supplying `target_location_id` must not make an incomplete Asset eligible, because that would mutate the business location later without the completion lifecycle and batch audit. Keep the explicit retained-location `None` guard in `asset_usage_service` as a defensive error for inconsistent legacy rows.

Add a RED regression test that sets an otherwise idle Asset's `location_id=None` and `data_completeness=INCOMPLETE`, submits personal usage with an explicit valid target location, and asserts the fixed incomplete-data error, unchanged Asset values/version, and zero `OperationRequest`, `OperationRequestAsset`, `AssetBusinessLock`, lifecycle, and operation-log rows. Add the same direct common-kernel assertion for a return operation type so the invariant is not personal-usage-specific.

Extend the real stock-in HTTP compatibility test to assert the submitted `StockInItem` has the category's `service_life_months`, calculated `expected_expiry_date`, and `{}` custom attributes. Change the category lifetime and commit before approval; after approval assert the new `Asset` still carries the frozen item values and `data_completeness=COMPLETE`. This is the immutable-snapshot regression, not a model-metadata test.

- [ ] **Step 6: Update only existing test factories that construct Asset or StockInItem**

Every direct constructor supplies deterministic values:

```python
service_life_months=36,
expected_expiry_date=date(2029, 1, 1),
custom_attributes={},
data_completeness=AssetDataCompleteness.COMPLETE.value,  # Asset only
```

Do not make production columns nullable merely to preserve old test factories.

- [ ] **Step 7: Run GREEN**

```bash
cd back
.venv/bin/python -m pytest tests/test_supplier_models.py tests/test_asset_data_foundation.py tests/test_stock_in_submit.py tests/test_stock_in_foundation_compat.py tests/test_asset_usage_service.py tests/test_asset_business_locks.py tests/test_asset_codes.py tests/test_asset_transition_contracts.py tests/test_asset_usage_return_models.py tests/test_asset_usage_return_schemas.py tests/test_assets.py tests/test_operation_api.py tests/test_operation_executor.py tests/test_operation_models.py tests/test_workflow_models.py -q
.venv/bin/python -m pytest -q
```

Expected: the complete affected set and then the full backend suite pass before this commit.

- [ ] **Step 8: Commit**

```bash
git add back/app/enums/__init__.py back/app/models/__init__.py back/app/models/asset.py back/app/models/workflow.py back/app/models/supplier.py back/app/services/__init__.py back/app/services/asset_data_service.py back/app/services/asset_service.py back/app/services/operation_service.py back/app/services/asset_usage_service.py back/app/services/stock_in_service.py back/tests/asset_usage_return_fixtures.py back/tests/test_asset_business_locks.py back/tests/test_asset_codes.py back/tests/test_asset_data_foundation.py back/tests/test_asset_transition_contracts.py back/tests/test_asset_usage_return_models.py back/tests/test_asset_usage_return_schemas.py back/tests/test_asset_usage_service.py back/tests/test_assets.py back/tests/test_operation_api.py back/tests/test_operation_executor.py back/tests/test_operation_models.py back/tests/test_stock_in_foundation_compat.py back/tests/test_supplier_models.py back/tests/test_workflow_models.py
git diff --cached --name-only
scripts/guard-conventions.sh
git commit -m "feat: define shared asset data models"
```

## Task 2: Add immutable Alembic revision 006

**Files:**

- Create: `back/migrations/versions/006_asset_data_foundation.py`
- Create: `back/tests/test_asset_data_migration.py`
- Modify: `back/tests/test_migrations.py`

- [ ] **Step 1: Write migration RED tests**

The revision contract is exact:

```python
def test_revision_006_follows_usage_return() -> None:
    module = load_migration("006_asset_data_foundation.py")
    assert module.revision == "006"
    assert module.down_revision == "005"
```

The SQLite round-trip test must:

1. upgrade a temporary database to 005;
2. insert one legacy Asset and one pending StockInItem;
3. upgrade to 006;
4. assert both supplier tables and the fixed `SUP` sequence row;
5. compare all 006 columns, nullability, indexes, unique indexes, and FKs with SQLAlchemy metadata;
6. assert Asset and StockInItem life values were copied from their category and expiry dates were calculated from their purchase dates;
7. assert `custom_attributes == {}` and legacy Asset completeness is `COMPLETE`;
8. assert all permission-role mappings below;
9. downgrade to 005, assert all 006-only objects and permissions are gone;
10. upgrade to 006 once more.

Assert these explicit index/FK names so model and migration cannot drift:

```text
ix_suppliers_code (unique)
ix_suppliers_name (unique)
ix_suppliers_unified_social_credit_code (unique)
ix_suppliers_status
ix_assets_supplier_id
ix_assets_data_completeness
ix_stock_in_items_supplier_id
fk_assets_supplier_id
fk_stock_in_items_supplier_id
```

```python
EXPECTED_ROLE_PERMISSIONS = {
    "supplier:view": {"SUPER_ADMIN", "ASSET_ADMIN", "USER"},
    "supplier:create": {"SUPER_ADMIN", "ASSET_ADMIN"},
    "supplier:edit": {"SUPER_ADMIN", "ASSET_ADMIN"},
    "supplier:disable": {"SUPER_ADMIN", "ASSET_ADMIN"},
    "supplier:delete": {"SUPER_ADMIN"},
    "asset:data:complete": {"SUPER_ADMIN", "ASSET_ADMIN"},
    "asset:service-life:update": {"SUPER_ADMIN", "ASSET_ADMIN"},
}
```

Freeze the complete permission-row contract as well as role mappings: all seven rows have `enabled = true`; the five `supplier:*` rows use module `supplier`; both `asset:*` rows use module `asset`; and names are exactly `查看供应商`, `新增供应商`, `编辑供应商`, `停用恢复供应商`, `删除供应商`, `补充资产资料`, and `调整资产使用期限` respectively.

The downgrade guard test sets an Asset reference to NULL after upgrading and asserts downgrade raises `RuntimeError` containing `unit_id/source_id/location_id`. After the failure, assert `alembic_version` is still `006` and that both supplier tables, every 006 column/index/FK, every permission row, and every role mapping remain unchanged. This proves the preflight fails before any DML or DDL.

The MySQL offline tests stub data backfill, permission DML, and the downgrade preflight query; compile both `upgrade()` and `downgrade()` under a MySQL `MigrationContext`; assert the expected tables, JSON columns, FKs, ALTER statements, and indexes compile; and assert every supplier FK is dropped before its backing index.

- [ ] **Step 2: Run RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_asset_data_migration.py -q
```

Expected: failure because revision 006 is missing.

- [ ] **Step 3: Implement the additive and backfill phases**

Use this exact phase order in `upgrade()`:

```python
def upgrade() -> None:
    _create_supplier_tables()
    _add_nullable_asset_columns()
    _add_nullable_stock_in_columns()
    _backfill_existing_rows()
    _enforce_final_nullability()
    _seed_permissions()
```

The supplier tables match Task 1. Seed the sequence without a fixed generated supplier ID:

```python
bind.execute(
    sa.text(
        "INSERT INTO supplier_code_sequences "
        "(prefix, current_value, created_at, updated_at) "
        "SELECT 'SUP', 0, :now, :now WHERE NOT EXISTS ("
        "SELECT 1 FROM supplier_code_sequences WHERE prefix = 'SUP')"
    ),
    {"now": now},
)
```

Initially add these columns as nullable:

```text
assets:
  supplier_id INTEGER NULL FK suppliers.id RESTRICT + index
  service_life_months INTEGER NULL
  expected_expiry_date DATE NULL
  custom_attributes JSON NULL
  data_completeness VARCHAR(16) NULL + index

stock_in_items:
  supplier_id INTEGER NULL FK suppliers.id RESTRICT + index
  supplier_snapshot JSON NULL
  service_life_months INTEGER NULL
  expected_expiry_date DATE NULL
  custom_attributes JSON NULL
```

Backfill in Python so SQLite and MySQL have identical end-of-month behavior:

```python
def _expiry(purchase_date: date, months: int) -> date:
    month_index = purchase_date.year * 12 + purchase_date.month - 1 + months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    return date(year, month, min(purchase_date.day, monthrange(year, month)[1]))
```

Read each legacy row joined to `asset_categories`, then update it with the category's `service_life_months`, the calculated date, `{}`, and `COMPLETE`. Do the same life/date/custom-attribute backfill for every legacy StockInItem. Bind JSON through a typed SQLAlchemy table (or an explicitly typed bind parameter), never through an untyped `sa.text` dict parameter:

```python
assets_table = sa.table(
    "assets",
    sa.column("id", sa.Integer()),
    sa.column("custom_attributes", sa.JSON()),
)
bind.execute(
    assets_table.update()
    .where(assets_table.c.id == sa.bindparam("asset_id"))
    .values(
        custom_attributes=sa.bindparam("custom_attributes_value", type_=sa.JSON())
    ),
    {"asset_id": asset_id, "custom_attributes_value": {}},
)
```

After backfill, use `batch_alter_table` to:

- make Asset `unit_id/source_id/location_id` nullable;
- make Asset life/date/custom/completeness non-null;
- make StockInItem life/date/custom non-null.

Every MySQL-sensitive `alter_column` supplies the exact `existing_type` and `existing_nullable` values. Do not add a server default for JSON or dates.

- [ ] **Step 4: Implement permission seeds and safe downgrade**

Seed by code and role code using the same idempotent `INSERT ... SELECT ... NOT EXISTS` pattern as revision 005.

Downgrade order is exact:

```python
def downgrade() -> None:
    _assert_legacy_references_are_complete()
    _delete_permission_assignments_then_permissions()
    _drop_stock_in_columns_and_constraints()
    _drop_asset_columns_and_constraints_and_restore_reference_nullability()
    op.drop_table("suppliers")
    op.drop_table("supplier_code_sequences")
```

The precheck runs before destructive DDL:

```python
missing = bind.scalar(
    sa.text(
        "SELECT COUNT(*) FROM assets "
        "WHERE unit_id IS NULL OR source_id IS NULL OR location_id IS NULL"
    )
)
if missing:
    raise RuntimeError(
        "cannot downgrade 006: assets contain NULL unit_id/source_id/location_id"
    )
```

Drop each FK and explicit index before its column. Do not touch `asset_code_reservations`.

- [ ] **Step 5: Run migration GREEN**

```bash
cd back
.venv/bin/python -m pytest tests/test_asset_data_migration.py tests/test_migrations.py -q
export SMOKE_ROOT="$(mktemp -d /private/tmp/asset-data-006.XXXXXX)"
touch "$SMOKE_ROOT/empty.env"
export ENV_FILE="$SMOKE_ROOT/empty.env"
export DB_URL="sqlite:///$SMOKE_ROOT/asset-data.db"
export FLASK_ENV=dev
.venv/bin/python -c 'import os; from pathlib import Path; root=Path(os.environ["SMOKE_ROOT"]).resolve(); db=Path(os.environ["DB_URL"].removeprefix("sqlite:///")).resolve(); assert db.is_relative_to(root)'
FLASK_APP=manage.py .venv/bin/flask db upgrade
FLASK_APP=manage.py .venv/bin/flask db check
```

Expected: tests pass, the disposable database is upgraded to 006, and Alembic reports no metadata drift. Never run this check against the default dev database.

- [ ] **Step 6: Commit**

```bash
git add back/migrations/versions/006_asset_data_foundation.py back/tests/test_asset_data_migration.py back/tests/test_migrations.py
git diff --cached --name-only
scripts/guard-conventions.sh
git commit -m "feat: migrate shared asset data foundation"
```

## Task 3: Implement supplier business use cases

**Files:**

- Create: `back/app/repositories/supplier_repository.py`
- Create: `back/app/services/supplier_service.py`
- Create: `back/tests/test_suppliers.py`
- Modify: `back/app/repositories/asset_repository.py`
- Modify: `back/app/repositories/workflow_repository.py`
- Modify: `back/app/services/audit_service.py`
- Modify: repository/service exports

- [ ] **Step 1: Write failing service tests**

Cover these behaviors with real database rows:

```python
def test_supplier_code_is_monotonic_after_delete(app, supplier_actor) -> None:
    first = supplier_service.create_supplier({"name": "甲供应商"}, supplier_actor.id)
    supplier_service.delete_supplier(
        first["id"], first["version"], supplier_actor.id, "录入错误"
    )
    second = supplier_service.create_supplier({"name": "乙供应商"}, supplier_actor.id)
    assert first["code"] == "SUP000001"
    assert second["code"] == "SUP000002"


def test_disabled_duplicate_must_be_restored_not_recreated(app, supplier_actor) -> None:
    created = supplier_service.create_supplier({"name": "  上海供应商  "}, supplier_actor.id)
    supplier_service.set_supplier_enabled(
        created["id"], False, created["version"], supplier_actor.id
    )
    with pytest.raises(BusinessException, match="恢复启用"):
        supplier_service.create_supplier({"name": "上海供应商"}, supplier_actor.id)


def test_supplier_delete_refuses_asset_or_stock_in_history(app, supplier_actor) -> None:
    supplier = create_referenced_supplier()
    with pytest.raises(BusinessException, match="已被使用"):
        supplier_service.delete_supplier(
            supplier.id, supplier.version, supplier_actor.id, "清理"
        )


def test_every_supplier_change_writes_audit_logs(app, supplier_actor) -> None:
    created = supplier_service.create_supplier(
        {
            "name": "审计供应商",
            "contact_name": "敏感联系人",
            "contact_phone": "13812345678",
            "address": "敏感详细地址",
        },
        supplier_actor.id,
    )
    updated = supplier_service.update_supplier(
        created["id"], {"name": "审计供应商二", "version": 1}, supplier_actor.id
    )
    disabled = supplier_service.set_supplier_enabled(
        created["id"], False, updated["version"], supplier_actor.id
    )
    enabled = supplier_service.set_supplier_enabled(
        created["id"], True, disabled["version"], supplier_actor.id
    )
    supplier_service.delete_supplier(
        created["id"], enabled["version"], supplier_actor.id, "录入错误"
    )
    logs = list(reversed(operation_log_repository.list_recent()))
    assert [item.action for item in logs] == [
        "SUPPLIER_CREATE",
        "SUPPLIER_UPDATE",
        "SUPPLIER_DISABLE",
        "SUPPLIER_ENABLE",
        "SUPPLIER_DELETE",
    ]
    assert all(item.resource_id == str(created["id"]) for item in logs)
    assert logs[0].before_data is None and logs[0].after_data is not None
    assert logs[1].before_data is not None and logs[1].after_data is not None
    assert logs[-1].reason == "录入错误"
    serialized_logs = json.dumps(
        [item.before_data for item in logs] + [item.after_data for item in logs],
        ensure_ascii=False,
    )
    assert "13812345678" not in serialized_logs
    assert "敏感联系人" not in serialized_logs
    assert "敏感详细地址" not in serialized_logs
```

Also cover uppercase/trim normalization of social credit code, name/credit uniqueness, blank-name/reason rejection after trimming, optimistic version rejection, permissions, disable/enable, and a disabled supplier rejected by `require_enabled_supplier`.

Mirror `test_asset_codes.py::test_first_sequence_allocation_is_safe_across_independent_transactions` with a file-backed SQLite app, two worker transactions, and a Barrier; assert the two supplier codes are exactly `SUP000001` and `SUP000002`, and the persistent sequence ends at 2.

Add a second independent-transaction Barrier test in which both workers attempt `cas_update` with the same supplier/version. Exactly one update returns true/commits, the other returns false and rolls back, the final version increments once, and no update is lost.

- [ ] **Step 2: Run RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_suppliers.py -q
```

Expected: import failures for the new repository and service.

- [ ] **Step 3: Implement the code sequence and supplier repository**

```python
class SupplierCodeSequenceRepository(BaseRepository[SupplierCodeSequence]):
    def __init__(self) -> None:
        super().__init__(SupplierCodeSequence)

    def ensure_exists(self) -> None:
        values = {"prefix": "SUP", "current_value": 0}
        dialect = db.session.get_bind().dialect.name
        if dialect == "mysql":
            from sqlalchemy.dialects.mysql import insert as mysql_insert

            statement = mysql_insert(SupplierCodeSequence).values(**values)
            db.session.execute(
                statement.on_duplicate_key_update(
                    current_value=SupplierCodeSequence.current_value
                )
            )
        elif dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert

            statement = sqlite_insert(SupplierCodeSequence).values(**values)
            db.session.execute(
                statement.on_conflict_do_nothing(index_elements=["prefix"])
            )
        else:
            raise RuntimeError(f"unsupported database dialect: {dialect}")

    def find_for_update(self) -> SupplierCodeSequence | None:
        return db.session.scalar(
            select(SupplierCodeSequence)
            .where(SupplierCodeSequence.prefix == "SUP")
            .with_for_update()
        )


class SupplierRepository(BaseRepository[Supplier]):
    def __init__(self) -> None:
        super().__init__(Supplier)

    def find_by_code(self, code: str) -> Supplier | None:
        return self.find_one(Supplier.code == code)

    def find_by_name(self, value: str) -> Supplier | None:
        return self.find_one(Supplier.name == value)

    def find_by_credit_code(self, value: str) -> Supplier | None:
        return self.find_one(Supplier.unified_social_credit_code == value)

    def list_all(self) -> list[Supplier]:
        statement = select(Supplier).order_by(Supplier.code.asc())
        return list(db.session.scalars(statement).all())

    def find_for_update(self, supplier_id: int) -> Supplier | None:
        return db.session.scalar(
            select(Supplier).where(Supplier.id == supplier_id).with_for_update()
        )

    def cas_update(
        self,
        supplier_id: int,
        expected_version: int,
        changes: Mapping[str, object],
    ) -> bool:
        allowed = {
            "name",
            "unified_social_credit_code",
            "contact_name",
            "contact_phone",
            "address",
            "remark",
            "status",
        }
        if not changes or set(changes) - allowed:
            raise BusinessException("供应商更新字段无效")
        result = db.session.execute(
            update(Supplier)
            .where(Supplier.id == supplier_id, Supplier.version == expected_version)
            .values(**dict(changes), version=Supplier.version + 1)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1
```

The lookup methods use direct equality and the list is ordered by `Supplier.code.asc()`; no fuzzy matching is introduced.

Add reference checks to the owning repositories:

```python
# AssetRepository
def has_supplier_reference(self, supplier_id: int) -> bool:
    return db.session.scalar(
        select(Asset.id).where(Asset.supplier_id == supplier_id).limit(1)
    ) is not None

# StockInItemRepository
def has_supplier_reference(self, supplier_id: int) -> bool:
    return db.session.scalar(
        select(StockInItem.id).where(StockInItem.supplier_id == supplier_id).limit(1)
    ) is not None
```

- [ ] **Step 4: Add reusable audit staging**

```python
def record_resource_change(
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    actor_id: int,
    before_data: Mapping[str, Any] | None,
    after_data: Mapping[str, Any] | None,
    reason: str | None = None,
) -> None:
    operation_log_repository.add(
        OperationLog(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            operator_id=actor_id,
            before_data=dict(before_data) if before_data is not None else None,
            after_data=dict(after_data) if after_data is not None else None,
            reason=reason,
        )
    )
```

This function stages only; the calling use case owns the commit.

Supplier audit payloads never reuse the API serializer. Define `_supplier_audit_snapshot(supplier)` to include only `id`, `code`, `name`, `unified_social_credit_code`, `status`, `version`, and a masked `contact_phone` (`138****5678`; shorter non-empty values become all `*`). Omit contact name, address, and free-text remark entirely. Tests serialize all before/after JSON and prove the original phone, contact name, and address never appear.

- [ ] **Step 5: Implement supplier_service with exact public signatures**

```text
require_enabled_supplier(supplier_id: int) -> Supplier
list_suppliers(actor_id: int) -> list[dict[str, Any]]
create_supplier(payload: dict[str, Any], actor_id: int) -> dict[str, Any]
update_supplier(supplier_id: int, payload: dict[str, Any], actor_id: int) -> dict[str, Any]
set_supplier_enabled(supplier_id: int, enabled: bool, expected_version: int, actor_id: int) -> dict[str, Any]
delete_supplier(supplier_id: int, expected_version: int, actor_id: int, reason: str) -> None
```

Normalization and allocation are deterministic:

```python
def _normalized_name(value: object) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise BusinessException("供应商名称不能为空", result_code=ResultCode.BAD_REQUEST)
    return normalized


def _normalized_credit_code(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized or None


def _allocate_code() -> str:
    supplier_code_sequence_repository.ensure_exists()
    sequence = supplier_code_sequence_repository.find_for_update()
    if sequence is None:
        raise RuntimeError("supplier code sequence was not initialized")
    sequence.current_value += 1
    return f"{sequence.prefix}{sequence.current_value:06d}"
```

Update and enable/disable use `cas_update`; a zero row count becomes the standard stale-version `BusinessException` and the service rolls back. Delete first locks the Supplier row, compares `expected_version`, then checks Asset and StockInItem references and deletes in the same transaction. Convert recognized unique-index races to `BusinessException("供应商已存在")` and delete/FK races to `BusinessException("供应商已被使用，不能删除")`; always roll back and raise from `None` without exposing SQL text. Each successful use case checks its exact permission, stages a masked `OperationLog` via `record_resource_change`, and commits once.

- [ ] **Step 6: Run GREEN**

```bash
cd back
.venv/bin/python -m pytest tests/test_suppliers.py tests/test_supplier_models.py -q
```

Expected: all supplier service tests pass.

- [ ] **Step 7: Commit**

```bash
git add back/app/repositories/supplier_repository.py back/app/repositories/asset_repository.py back/app/repositories/workflow_repository.py back/app/repositories/__init__.py back/app/services/supplier_service.py back/app/services/audit_service.py back/app/services/__init__.py back/tests/test_suppliers.py
git diff --cached --name-only
scripts/guard-conventions.sh
git commit -m "feat: manage supplier master data"
```

## Task 4: Expose the standalone supplier API

**Files:**

- Create: `back/app/schemas/supplier.py`
- Create: `back/app/api/suppliers.py`
- Modify: `back/app/schemas/__init__.py`
- Modify: `back/app/api/__init__.py`
- Modify: `back/tests/test_suppliers.py`

- [ ] **Step 1: Write failing HTTP tests**

Create the test actor with `hash_password("admin123")`, not a fixed bcrypt fixture. Verify:

```python
created = client.post("/api/v1/suppliers", headers=headers, json={"name": "接口供应商"})
updated = client.post(
    f"/api/v1/suppliers/{created.get_json()['data']['id']}/update",
    headers=headers,
    json={"name": "接口供应商有限公司", "version": 1},
)
listed = client.get("/api/v1/suppliers", headers=headers)
disabled = client.post(
    f"/api/v1/suppliers/{created.get_json()['data']['id']}/disable",
    headers=headers,
    json={"version": updated.get_json()["data"]["version"]},
)
deleted = client.post(
    f"/api/v1/suppliers/{created.get_json()['data']['id']}/delete",
    headers=headers,
    json={
        "version": disabled.get_json()["data"]["version"],
        "reason": "测试删除",
    },
)
assert created.status_code == updated.status_code == listed.status_code == 200
assert disabled.status_code == deleted.status_code == 200
```

Also assert no token returns HTTP 401; missing functional permission returns HTTP 200 with envelope `code == 403`; malformed payload and create/update/delete payloads containing only whitespace for required name/reason return HTTP 400; and no PUT/PATCH/DELETE route is registered.

- [ ] **Step 2: Run RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_suppliers.py -k http -q
```

Expected: 404 because the Blueprint is not registered.

- [ ] **Step 3: Add exact request schemas**

```python
class CreateSupplierRequestSchema(Schema):
    name = fields.String(
        required=True,
        validate=validate.And(
            validate.Length(max=255),
            validate.Predicate("strip", error="供应商名称不能为空"),
        ),
    )
    unified_social_credit_code = fields.String(required=False, allow_none=True, validate=validate.Length(max=64))
    contact_name = fields.String(required=False, allow_none=True, validate=validate.Length(max=128))
    contact_phone = fields.String(required=False, allow_none=True, validate=validate.Length(max=64))
    address = fields.String(required=False, allow_none=True, validate=validate.Length(max=500))
    remark = fields.String(required=False, allow_none=True, validate=validate.Length(max=1000))


class UpdateSupplierRequestSchema(CreateSupplierRequestSchema):
    version = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))


class SupplierVersionRequestSchema(Schema):
    version = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))


class DeleteSupplierRequestSchema(SupplierVersionRequestSchema):
    reason = fields.String(
        required=True,
        validate=validate.And(
            validate.Length(max=500),
            validate.Predicate("strip", error="删除原因不能为空"),
        ),
    )
```

- [ ] **Step 4: Add GET/POST-only routes and registration**

```python
bp = Blueprint("suppliers", __name__, url_prefix="/api/v1/suppliers")


@bp.get("")
@jwt_required()
def list_suppliers() -> dict:
    return Result.success(supplier_service.list_suppliers(current_user_id())).to_dict()


@bp.post("")
@jwt_required()
def create_supplier() -> dict:
    payload = _create_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        supplier_service.create_supplier(payload, current_user_id())
    ).to_dict()
```

Add POST `/<int:supplier_id>/update`, `/disable`, `/enable`, and `/delete`. Disable/enable load `SupplierVersionRequestSchema`. Trim `name` and `reason` before passing them to the service; the service repeats nonblank validation defensively. Delete loads `DeleteSupplierRequestSchema` and calls:

```python
supplier_service.delete_supplier(
    supplier_id, payload["version"], current_user_id(), payload["reason"].strip()
)
return Result.success().to_dict()
```

Import `suppliers` and register `app.register_blueprint(suppliers.bp)` in `back/app/api/__init__.py`, matching the existing module pattern. `create_app()` already calls `register_blueprints`, so this task does not modify `back/app/__init__.py`.

- [ ] **Step 5: Run GREEN**

```bash
cd back
.venv/bin/python -m pytest tests/test_suppliers.py -q
```

Expected: supplier tests pass.

- [ ] **Step 6: Commit**

```bash
git add back/app/api/suppliers.py back/app/schemas/supplier.py back/app/api/__init__.py back/app/schemas/__init__.py back/tests/test_suppliers.py
git diff --cached --name-only
scripts/guard-conventions.sh
git commit -m "feat: expose supplier master data api"
```

## Task 5: Centralize asset access and completeness calculations

**Files:**

- Create: `back/app/services/asset_access_service.py`
- Modify: `back/app/services/asset_data_service.py`
- Modify: `back/app/repositories/asset_repository.py`
- Modify: `back/app/services/asset_service.py`
- Modify: `back/app/schemas/asset.py`
- Modify: `back/app/api/assets.py`
- Modify: service exports and `back/tests/test_asset_data_foundation.py`

- [ ] **Step 1: Write failing scope, date, serialization, and filter tests**

```python
def test_expected_expiry_clamps_end_of_month() -> None:
    assert calculate_expected_expiry(date(2024, 2, 29), 12) == date(2025, 2, 28)
    assert calculate_expected_expiry(date(2026, 1, 31), 1) == date(2026, 2, 28)


def test_self_scope_contains_holder_or_manager(
    app, self_actor, other_user, asset_factory
) -> None:
    held = asset_factory(holder_user_id=self_actor.id, manager_id=other_user.id)
    managed = asset_factory(holder_user_id=None, manager_id=self_actor.id)
    hidden = asset_factory(holder_user_id=other_user.id, manager_id=other_user.id)
    visible = asset_repository.find_all(
        QuerySpec(filters=[asset_access_service.access_filter(self_actor.id)])
    )
    visible_ids = {asset.id for asset in visible}
    assert visible_ids == {held.id, managed.id}
```

Add separate tests for DEPARTMENT + SELF OR semantics, ALL scope, no scope, `get_accessible` returning NOT_FOUND outside scope, new output fields, exact `missing_fields` names, amount masking unchanged, and exact `data_completeness=INCOMPLETE` page filtering.

- [ ] **Step 2: Run RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_asset_data_foundation.py tests/test_assets.py -q
```

Expected: imports or assertions fail because the shared services and fields are not wired.

- [ ] **Step 3: Extend the existing pure calculation module**

```python
# calculate_expected_expiry already exists from Task 1; keep it unchanged.


def calculate_completeness_values(
    unit_id: int | None,
    source_id: int | None,
    location_id: int | None,
) -> str:
    if unit_id is not None and source_id is not None and location_id is not None:
        return AssetDataCompleteness.COMPLETE.value
    return AssetDataCompleteness.INCOMPLETE.value


def missing_fields(
    unit_id: int | None,
    source_id: int | None,
    location_id: int | None,
) -> list[str]:
    values = {
        "unit_id": unit_id,
        "source_id": source_id,
        "location_id": location_id,
    }
    return [name for name, value in values.items() if value is None]
```

- [ ] **Step 4: Implement one reusable SQL access filter**

```python
def access_filter(actor_id: int) -> ColumnElement[bool]:
    organization_ids = permission_service.accessible_organization_ids(actor_id)
    if organization_ids is None:
        return Asset.id.is_not(None)
    conditions: list[ColumnElement[bool]] = []
    if organization_ids:
        conditions.append(Asset.organization_id.in_(organization_ids))
    if DataScope.SELF.value in permission_service.get_data_scopes(actor_id):
        conditions.append(
            or_(Asset.manager_id == actor_id, Asset.holder_user_id == actor_id)
        )
    return or_(*conditions) if conditions else false()


def get_accessible(
    asset_id: int,
    actor_id: int,
    permission_code: str = "asset:view",
) -> Asset:
    permission_service.require_permission(actor_id, permission_code)
    asset = asset_repository.find_accessible(asset_id, access_filter(actor_id))
    if asset is None:
        raise BusinessException("资产不存在", result_code=ResultCode.NOT_FOUND)
    return asset
```

Add `find_many_accessible_for_update(asset_ids, access_filter)` to AssetRepository using sorted unique IDs, the supplied SQL predicate, `order_by(Asset.id.asc())`, and `with_for_update()`.

- [ ] **Step 5: Replace the private asset_service filter and add output/query fields**

```python
result.update(
    {
        "supplier_id": asset.supplier_id,
        "service_life_months": asset.service_life_months,
        "expected_expiry_date": asset.expected_expiry_date.isoformat(),
        "custom_attributes": dict(asset.custom_attributes),
        "data_completeness": asset.data_completeness,
        "missing_fields": asset_data_service.missing_fields(
            asset.unit_id, asset.source_id, asset.location_id
        ),
    }
)
```

Add a `data_completeness` `OneOf` field to `AssetPageQuerySchema`, pass it through `api/assets.py`, and add the exact equality predicate in `asset_service.page`. Keep all filtering in SQL.

- [ ] **Step 6: Run GREEN**

```bash
cd back
.venv/bin/python -m pytest tests/test_asset_data_foundation.py tests/test_assets.py -q
```

Expected: focused tests pass.

- [ ] **Step 7: Commit**

```bash
git add back/app/services/asset_access_service.py back/app/services/asset_data_service.py back/app/services/asset_service.py back/app/repositories/asset_repository.py back/app/schemas/asset.py back/app/api/assets.py back/app/services/__init__.py back/tests/test_asset_data_foundation.py back/tests/test_assets.py
git diff --cached --name-only
scripts/guard-conventions.sh
git commit -m "feat: centralize asset data access"
```

## Task 6: Add null-only single and batch data completion

**Files:**

- Create: `back/app/services/asset_data_completion_service.py`
- Create: `back/tests/test_asset_data_completion.py`
- Modify: `back/app/repositories/asset_repository.py`
- Modify: `back/app/services/audit_service.py`
- Modify: `back/app/schemas/asset.py`
- Modify: `back/app/api/assets.py`
- Modify: service/schema exports

- [ ] **Step 1: Write failing completion tests**

Cover:

```python
def test_single_completion_changes_only_null_fields_and_audits(
    client, incomplete_asset, admin_headers, enabled_unit
):
    response = client.post(
        f"/api/v1/assets/{incomplete_asset.id}/complete-data",
        headers=admin_headers,
        json={"version": incomplete_asset.version, "unit_id": enabled_unit.id},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["unit_id"] == enabled_unit.id


def test_batch_completion_is_atomic_on_one_stale_version(
    client,
    incomplete_asset_factory,
    admin_headers,
    enabled_source,
):
    first = incomplete_asset_factory(source_id=None)
    second = incomplete_asset_factory(source_id=None)
    stale_second_version = second.version
    second.version += 1
    db.session.commit()
    response = client.post(
        "/api/v1/assets/complete-data",
        headers=admin_headers,
        json={
            "items": [
                {"asset_id": first.id, "version": first.version},
                {"asset_id": second.id, "version": stale_second_version},
            ],
            "source_id": enabled_source.id,
        },
    )
    assert response.status_code == 200
    assert response.get_json()["code"] == ResultCode.BUSINESS_ERROR.code
    db.session.expire_all()
    assert db.session.get(Asset, first.id).source_id is None
    assert db.session.get(Asset, second.id).source_id is None
```

Also test: at least one field required; explicit NULL rejected; disabled dictionary value rejected; non-null overwrite rejected; out-of-scope asset hidden as NOT_FOUND; active business lock rejected; duplicate asset IDs rejected; holder-only SELF access; CAS conflict; max 100; one lifecycle row per asset; exactly one batch `OperationLog`; completeness changes to COMPLETE only when all three values exist.

- [ ] **Step 2: Run RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_asset_data_completion.py -q
```

Expected: 404 or missing service/repository methods.

- [ ] **Step 3: Add exact schemas**

```python
class _CompletionFieldsSchema(Schema):
    unit_id = fields.Integer(required=False, allow_none=False, strict=True)
    source_id = fields.Integer(required=False, allow_none=False, strict=True)
    location_id = fields.Integer(required=False, allow_none=False, strict=True)

    @validates_schema
    def require_change(self, data: dict, **_kwargs) -> None:
        if not {"unit_id", "source_id", "location_id"} & data.keys():
            raise ValidationError("至少填写一个待补充字段")


class CompleteAssetDataRequestSchema(_CompletionFieldsSchema):
    version = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))


class AssetVersionTargetSchema(Schema):
    asset_id = fields.Integer(required=True, strict=True)
    version = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))


class BatchCompleteAssetDataRequestSchema(_CompletionFieldsSchema):
    items = fields.List(
        fields.Nested(AssetVersionTargetSchema),
        required=True,
        validate=validate.Length(min=1, max=100),
    )
```

- [ ] **Step 4: Add the dedicated CAS without widening the operation-kernel CAS**

```python
def complete_missing_fields(
    self,
    asset_id: int,
    expected_version: int,
    changes: Mapping[str, int],
    resulting_completeness: str,
) -> bool:
    allowed = {"unit_id", "source_id", "location_id"}
    if not changes or set(changes) - allowed:
        raise BusinessException("待补充字段无效")
    predicates: list[ColumnElement[bool]] = [
        Asset.id == asset_id,
        Asset.version == expected_version,
    ]
    predicates.extend(getattr(Asset, key).is_(None) for key in changes)
    result = db.session.execute(
        update(Asset)
        .where(*predicates)
        .values(
            **dict(changes),
            data_completeness=resulting_completeness,
            version=Asset.version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1
```

Do not add these fields to the existing `_CAS_FIELDS`.

- [ ] **Step 5: Implement one atomic completion engine**

```python
_FIELDS = ("unit_id", "source_id", "location_id")


def complete_data(
    asset_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    batch_payload = {
        "items": [{"asset_id": asset_id, "version": payload["version"]}],
        **{key: payload[key] for key in _FIELDS if key in payload},
    }
    return complete_data_batch(batch_payload, actor_id)["items"][0]


def complete_data_batch(
    payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    try:
        permission_service.require_permission(actor_id, "asset:data:complete")
        changes = {key: payload[key] for key in _FIELDS if key in payload}
        targets: dict[int, int] = {}
        for item in payload["items"]:
            asset_id = item["asset_id"]
            if asset_id in targets:
                raise BusinessException("资产不能重复选择")
            targets[asset_id] = item["version"]

        if "unit_id" in changes:
            master_data_service.require_enabled_unit(changes["unit_id"])
        if "source_id" in changes:
            master_data_service.require_enabled_source(changes["source_id"])
        if "location_id" in changes:
            master_data_service.require_selectable_location(changes["location_id"])

        asset_ids = sorted(targets)
        assets = asset_repository.find_many_accessible_for_update(
            asset_ids, asset_access_service.access_filter(actor_id)
        )
        if [asset.id for asset in assets] != asset_ids:
            raise BusinessException("资产不存在", result_code=ResultCode.NOT_FOUND)
        locks = asset_business_lock_repository.find_by_assets(asset_ids)
        if locks:
            locked = {asset.id: asset.asset_code for asset in assets}
            raise BusinessException(
                f"资产 {locked[locks[0].asset_id]} 正在处理其它业务"
            )

        batch_no = (
            f"ADC{datetime.now(tz=timezone.utc):%Y%m%d}"
            f"{uuid4().hex[:12].upper()}"
        )
        prepared: list[
            tuple[
                Asset,
                dict[str, int | None],
                str,
                dict[str, Any],
                dict[str, Any],
            ]
        ] = []
        for asset in assets:
            expected_version = targets[asset.id]
            if asset.version != expected_version:
                raise BusinessException(
                    f"资产 {asset.asset_code} 已被修改，请刷新后重试"
                )
            for field_name in changes:
                if getattr(asset, field_name) is not None:
                    raise BusinessException(
                        f"资产 {asset.asset_code} 的 {field_name} 已有值，不能通过补齐覆盖"
                    )
            resulting_values = {
                "unit_id": changes.get("unit_id", asset.unit_id),
                "source_id": changes.get("source_id", asset.source_id),
                "location_id": changes.get("location_id", asset.location_id),
            }
            completeness = asset_data_service.calculate_completeness_values(
                resulting_values["unit_id"],
                resulting_values["source_id"],
                resulting_values["location_id"],
            )
            before_data = {
                **{field_name: None for field_name in changes},
                "data_completeness": asset.data_completeness,
                "version": asset.version,
            }
            after_data = {
                **changes,
                "data_completeness": completeness,
                "version": asset.version + 1,
            }
            prepared.append(
                (asset, resulting_values, completeness, before_data, after_data)
            )

        result_items: list[dict[str, Any]] = []
        for asset, resulting_values, completeness, before_data, after_data in prepared:
            if not asset_repository.complete_missing_fields(
                asset.id, asset.version, changes, completeness
            ):
                raise BusinessException(
                    f"资产 {asset.asset_code} 已被修改，请刷新后重试"
                )
            audit_service.record_asset_lifecycle(
                asset_id=asset.id,
                operation_type="ASSET_DATA_COMPLETE",
                request_no=batch_no,
                actor_id=actor_id,
                before_data=before_data,
                after_data=after_data,
            )
            result_items.append(
                {
                    "id": asset.id,
                    **resulting_values,
                    "data_completeness": completeness,
                    "version": asset.version + 1,
                }
            )

        audit_service.record_resource_change(
            action="ASSET_DATA_COMPLETE",
            resource_type="asset_data_completion_batch",
            resource_id=batch_no,
            actor_id=actor_id,
            before_data={"asset_ids": asset_ids, "fields": sorted(changes)},
            after_data={"updated_count": len(asset_ids)},
        )
        db.session.commit()
        return {
            "batch_no": batch_no,
            "updated_count": len(result_items),
            "items": result_items,
        }
    except Exception:
        db.session.rollback()
        raise
```

The engine validates the complete locked batch before issuing its first Core UPDATE. The single `try/except` starts before the first permission/repository query, encloses row locking, all preflight validation, mutation, audit, and commit, and explicitly rolls back every exception. Thus NOT_FOUND, active-lock, stale-version, non-null-overwrite, and CAS-race failures cannot leak an active transaction or row lock when the service is called directly outside a request teardown. For direct-service active-lock and stale-version tests, assert `db.session().in_transaction() is False` immediately after the expected exception. This is the authoritative unit-level assertion: the default SQLite `StaticPool` can make distinct ORM Session objects share one DBAPI connection, so a second Session is not presented as independent lock evidence. The stale-version atomicity test also calls `db.session.expire_all()` before re-reading rows to prove persisted state rather than an identity-map cache.

- [ ] **Step 6: Add the two POST routes**

```python
@bp.post("/assets/<int:asset_id>/complete-data")
@jwt_required()
def complete_data(asset_id: int) -> dict:
    payload = _complete_data_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        asset_data_completion_service.complete_data(
            asset_id, payload, current_user_id()
        )
    ).to_dict()


@bp.post("/assets/complete-data")
@jwt_required()
def complete_data_batch() -> dict:
    payload = _batch_complete_data_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        asset_data_completion_service.complete_data_batch(
            payload, current_user_id()
        )
    ).to_dict()
```

- [ ] **Step 7: Run GREEN**

```bash
cd back
.venv/bin/python -m pytest tests/test_asset_data_completion.py tests/test_asset_business_locks.py tests/test_assets.py -q
```

Expected: all focused tests pass.

- [ ] **Step 8: Commit**

```bash
git add back/app/services/asset_data_completion_service.py back/app/services/audit_service.py back/app/repositories/asset_repository.py back/app/schemas/asset.py back/app/api/assets.py back/app/services/__init__.py back/app/schemas/__init__.py back/tests/test_asset_data_completion.py
git diff --cached --name-only
scripts/guard-conventions.sh
git commit -m "feat: complete missing asset data"
```

## Task 7: Freeze supplier and service-life data at stock-in submission

**Files:**

- Modify: `back/app/schemas/stock_in.py`
- Modify: `back/app/services/stock_in_service.py`
- Modify: `back/app/services/asset_service.py`
- Modify: `back/app/services/asset_code_service.py`
- Modify: focused stock-in tests

- [ ] **Step 1: Write failing submit-to-execute snapshot tests**

```python
def test_stock_in_freezes_life_before_approval(client):
    context = _setup(client)
    supplier = Supplier(code="SUP000001", name="冻结供应商", status="ENABLED")
    db.session.add(supplier)
    db.session.commit()
    result = stock_in_service.submit(
        {
            "organization_id": context["organization"].id,
            "items": [{
                **_item(context),
                "supplier_id": supplier.id,
                "service_life_months": 24,
                "custom_attributes": {"color": "space-gray"},
            }],
        },
        context["applicant"].id,
    )
    context["category"].service_life_months = 120
    db.session.commit()
    stock_in_service.approve(result["id"], None, context["approver"].id)
    asset = db.session.scalar(select(Asset))
    assert asset.service_life_months == 24
    assert asset.expected_expiry_date == calculate_expected_expiry(
        asset.purchase_date, 24
    )
    assert asset.supplier_id == supplier.id
    assert asset.custom_attributes == {"color": "space-gray"}
```

Add tests for omitted service life defaulting to the category value, an explicit override succeeding with `asset:service-life:update`, a custom `stock-in:create` actor without that field permission being rejected, disabled supplier rejection, supplier snapshot containing only `id/code/name`, custom JSON over 16 KiB rejection, NaN/Infinity/nested non-JSON values being rejected, and unchanged required unit/source/location validation.

- [ ] **Step 2: Run RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_stock_in_submit.py tests/test_stock_in_e2e.py -q
```

Expected: new fields are rejected or not materialized.

- [ ] **Step 3: Extend the item schema**

```python
service_life_months = fields.Integer(
    required=False, strict=True, validate=validate.Range(min=1, max=1200)
)
supplier_id = fields.Integer(required=False, allow_none=True, strict=True)
custom_attributes = fields.Dict(
    keys=fields.String(validate=validate.Length(min=1, max=128)),
    values=fields.Raw(),
    load_default=dict,
)
```

In `StockInItemRequestSchema.validate_zero_amount`, serialize `custom_attributes` with compact UTF-8 JSON using `ensure_ascii=False`, separators `(",", ":")`, and `allow_nan=False`. Catch `TypeError`/`ValueError` and raise `ValidationError("自定义属性必须是合法JSON", field_name="custom_attributes")`; raise `ValidationError("自定义属性不能超过16KB", field_name="custom_attributes")` when the encoded UTF-8 length exceeds `16 * 1024`.

- [ ] **Step 4: Resolve and freeze values in _validate_item**

At the start of `submit`, before any allocation or write, require `asset:service-life:update` when any request item explicitly contains the `service_life_months` key. Omitted values require only the normal stock-in permission and use the category default. This is checked once for the whole request, and tests cover a custom role with `stock-in:create` but without the field permission.

```python
supplier_id = item.get("supplier_id")
supplier = (
    supplier_service.require_enabled_supplier(supplier_id)
    if supplier_id is not None
    else None
)
service_life_months = item.get(
    "service_life_months", category.service_life_months
)
normalized["supplier_id"] = supplier.id if supplier is not None else None
normalized["supplier_snapshot"] = (
    {"id": supplier.id, "code": supplier.code, "name": supplier.name}
    if supplier is not None
    else None
)
normalized["service_life_months"] = service_life_months
normalized["expected_expiry_date"] = asset_data_service.calculate_expected_expiry(
    item["purchase_date"], service_life_months
)
normalized["custom_attributes"] = dict(item.get("custom_attributes") or {})
```

Write those normalized values into `StockInItem`, and expose them from `_serialize_item`. The StockInItem row is the approval snapshot; no OperationRequestAsset row is invented for a not-yet-created Asset.

- [ ] **Step 5: Materialize only the frozen StockInItem values**

In `asset_service.stock_in_request()`, add:

```python
supplier_id=item.supplier_id,
service_life_months=item.service_life_months,
expected_expiry_date=item.expected_expiry_date,
custom_attributes=dict(item.custom_attributes),
data_completeness=AssetDataCompleteness.COMPLETE.value,
```

Do not query `AssetCategory` during execution. Keep `StockInHandler` unchanged; it continues to delegate to `asset_service.stock_in_request()`, and the operation executor owns the outer commit.

- [ ] **Step 6: Narrow the existing reservation entry point**

Rename only the current service function and its stock-in caller:

```python
def reserve_for_stock_in(
    operation_request_id: int,
    stock_in_item_id: int,
    allocated: AllocatedCode,
) -> AssetCodeReservation:
    reservation = AssetCodeReservation(
        operation_request_id=operation_request_id,
        stock_in_item_id=stock_in_item_id,
        asset_code=allocated.asset_code,
        sequence_value=allocated.sequence_value,
        status=AssetCodeStatus.PENDING_STOCK_IN.value,
    )
    asset_code_reservation_repository.add(reservation)
    return reservation
```

Update `stock_in_service.submit()` and focused tests to call `reserve_for_stock_in`. Update `asset_code_service.__all__` to export `reserve_for_stock_in` and remove `reserve`. Do not change `AssetCodeReservation` columns, foreign keys, or nullability in revision 006.

- [ ] **Step 7: Run GREEN and stock-in regression**

```bash
cd back
.venv/bin/python -m pytest tests/test_stock_in_submit.py tests/test_stock_in_e2e.py tests/test_stock_in_approval.py tests/test_stock_in_foundation_compat.py tests/test_asset_codes.py -q
```

Expected: all focused tests pass.

- [ ] **Step 8: Commit**

```bash
git add back/app/schemas/stock_in.py back/app/services/stock_in_service.py back/app/services/asset_service.py back/app/services/asset_code_service.py back/tests/test_stock_in_submit.py back/tests/test_stock_in_e2e.py back/tests/test_stock_in_approval.py back/tests/test_stock_in_foundation_compat.py back/tests/test_asset_codes.py
git diff --cached --name-only
scripts/guard-conventions.sh
git commit -m "feat: freeze stock in asset data"
```

## Task 8: Run the phase gate and real smoke

**Files:**

- Modify only files needed to correct failures attributable to Tasks 1–7.

- [ ] **Step 1: Run all static and diff gates**

```bash
cd back
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app/ config.py
cd ..
git diff --check 63fecb9
```

Expected: every command exits 0 with no warnings. Staged-file convention evidence is collected immediately before every task commit; invoking the guard against an empty index is not accepted as phase-gate evidence.

- [ ] **Step 2: Run migrations and the full backend suite**

```bash
cd back
export SMOKE_ROOT="$(mktemp -d /private/tmp/asset-data-gate.XXXXXX)"
touch "$SMOKE_ROOT/empty.env"
export ENV_FILE="$SMOKE_ROOT/empty.env"
export DB_URL="sqlite:///$SMOKE_ROOT/asset-data.db"
export FLASK_ENV=dev
.venv/bin/python -c 'import os; from pathlib import Path; root=Path(os.environ["SMOKE_ROOT"]).resolve(); db=Path(os.environ["DB_URL"].removeprefix("sqlite:///")).resolve(); assert db.is_relative_to(root)'
FLASK_APP=manage.py .venv/bin/flask db upgrade
FLASK_APP=manage.py .venv/bin/flask db check
.venv/bin/python -m pytest -q
```

Expected: Alembic head is 006, metadata has no drift, and the test count is greater than 463 with zero failures.

- [ ] **Step 3: Run an actual Flask HTTP smoke**

Keep the exact `SMOKE_ROOT`, empty `ENV_FILE`, `DB_URL`, and process environment from Step 2; start Flask on an unused port against that already-upgraded disposable SQLite database, then use HTTP to:

1. log in;
2. create a supplier;
3. create and approve stock-in with supplier, service life, and custom attributes;
4. fetch the Asset and verify all new serialized fields;
5. create an incomplete Asset through a test-only fixture/setup path;
6. complete it through the single POST endpoint and verify lifecycle and audit reads.

Stop the process after the smoke. Never print credentials or the database URL.

- [ ] **Step 4: Validate MySQL safely**

First compile revision 006 with the MySQL dialect. If the configured external MySQL user can create an isolated schema, create a uniquely named temporary schema, run `005 -> 006 -> 005 -> 006`, compare tables/indexes/FKs/permission rows, and drop only that temporary schema. Never run downgrade against an unknown or shared schema.

If isolated-schema creation is unavailable, record this as an external verification blocker; do not point migrations at the configured business schema.

- [ ] **Step 5: Commit gate-only corrections**

If corrections were needed, inspect `git status --short`, stage each repair-list path explicitly (never `git add back`, `back/tests`, or another directory), then compare `git diff --cached --name-only` with that repair list before running `scripts/guard-conventions.sh` and committing `fix: close asset data verification gaps`. Skip this commit when no correction was needed.

- [ ] **Step 6: Execute review loops**

For every implementation task, run spec-compliance review first, then code-quality review, and fix/re-review before advancing. After the whole phase, start one independent read-only reviewer for the required six dimensions:

1. requirement completeness;
2. logical correctness;
3. boundary cases;
4. code quality;
5. test coverage;
6. actual runtime results.

The reviewer returns a repair list only. The primary thread applies fixes, and the same reviewer rechecks until PASS or reports a concrete external blocker.
