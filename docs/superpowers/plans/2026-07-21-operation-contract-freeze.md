# Operation Contract Freeze Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze the minimum shared operation contracts required for asset usage/return, transfer, and repair to develop in parallel without modifying common kernel files.

**Architecture:** Keep business rules inside future feature services and handlers. This change adds only shared persisted execution mode, deterministic request creation, asset CAS primitives, lifecycle/audit writers, one-level asset-relation expansion, and a single approval-completion dispatch path. Existing stock-in behavior remains the compatibility contract.

**Tech Stack:** Python 3.13, Flask 3, SQLAlchemy 2, Alembic, marshmallow, pytest, Ruff, mypy.

---

## File map

**Create:**

- `back/app/services/asset_relation_service.py` — one-level main/attachment expansion only.
- `back/migrations/versions/004_operation_contract_freeze.py` — persisted approval execution mode.
- `back/tests/test_asset_transition_contracts.py` — row-lock, CAS, relation, and audit contracts.

**Modify:**

- `back/app/enums/__init__.py` — operation types, execution mode, confirmation trigger.
- `back/app/models/workflow.py` — `OperationRequest.approval_execution_mode`.
- `back/app/repositories/asset_repository.py` — ordered reads, row locks, CAS.
- `back/app/services/operation_service.py` — idempotent result object, target snapshots, multi-organization batches, shared approval dispatch.
- `back/app/services/operation_executor.py` — trigger/mode matrix, approval dispatch, manual confirmation.
- `back/app/services/approval_provider_service.py` — use shared approval dispatch.
- `back/app/services/stock_in_service.py` — use shared approval dispatch without behavior change.
- `back/app/services/audit_service.py` — generic lifecycle and operation audit writers.
- `back/app/services/__init__.py` — export relation service.
- `back/tests/test_operation_models.py` — persisted enum/model contracts.
- `back/tests/test_asset_business_locks.py` — request result, snapshots, mixed organizations, replay.
- `back/tests/test_operation_executor.py` — execution trigger/mode behavior.
- `back/tests/test_approval_providers.py` — FEISHU and DIRECT completion behavior.
- `back/tests/test_operation_api.py` — internal approval manual-confirm path.
- `back/tests/test_migrations.py` — revision 004 upgrade/downgrade.
- Existing tests containing `operation_service.create_request(...)` — adopt the new result and target mapping contract.

No feature models, APIs, permissions, real FEISHU integration, Redis, suppliers, attachments, or feature migration tables belong in this plan.

### Task 1: Persist execution mode and freeze enum values

**Files:**

- Modify: `back/app/enums/__init__.py`
- Modify: `back/app/models/workflow.py`
- Create: `back/migrations/versions/004_operation_contract_freeze.py`
- Modify: `back/tests/test_operation_models.py`
- Modify: `back/tests/test_migrations.py`

- [ ] **Step 1: Write failing enum and model contract tests**

Extend `test_operation_foundation_enums_expose_stable_persisted_values()` and `test_operation_request_has_lifecycle_and_idempotency_contract()`:

```python
assert _enum_values("OperationType") == {
    "STOCK_IN",
    "PERSONAL_USE",
    "PUBLIC_USE",
    "PERSONAL_RETURN",
    "PUBLIC_RETURN",
    "TRANSFER",
    "REPAIR_START",
    "REPAIR_COMPLETE",
}
assert _enum_values("ApprovalExecutionMode") == {
    "AUTO_ON_APPROVAL",
    "MANUAL_CONFIRM",
}
assert _enum_values("ExecutionTriggerType") == {
    "APPROVAL",
    "CONFIRMATION",
    "RETRY",
}

columns = _model("OperationRequest").__table__.columns
assert columns["approval_execution_mode"].nullable is False
assert columns["approval_execution_mode"].default.arg == "AUTO_ON_APPROVAL"
```

- [ ] **Step 2: Write the failing migration contract**

Add to `test_migrations.py`:

```python
CONTRACT_MIGRATION = (
    BACK_DIR / "migrations" / "versions" / "004_operation_contract_freeze.py"
)


def test_operation_contract_migration_follows_operation_foundation() -> None:
    assert CONTRACT_MIGRATION.is_file()
    spec = importlib.util.spec_from_file_location("migration_004", CONTRACT_MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "004"
    assert module.down_revision == "003"
```

In `test_migrations_upgrade_clean_sqlite_database()`, require `approval_execution_mode` in `operation_columns`.

Add a focused preservation test:

```python
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
```

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```bash
cd back
.venv/bin/python -m pytest \
  tests/test_operation_models.py::test_operation_foundation_enums_expose_stable_persisted_values \
  tests/test_operation_models.py::test_operation_request_has_lifecycle_and_idempotency_contract \
  tests/test_migrations.py::test_operation_contract_migration_follows_operation_foundation -q
```

Expected: failures for missing enum values, missing model column, and missing revision 004.

- [ ] **Step 4: Add the enum and model contracts**

Add to `app/enums/__init__.py` and its `__all__`:

```python
class ApprovalExecutionMode(StringEnum):
    AUTO_ON_APPROVAL = "AUTO_ON_APPROVAL"
    MANUAL_CONFIRM = "MANUAL_CONFIRM"


class ExecutionTriggerType(StringEnum):
    APPROVAL = "APPROVAL"
    CONFIRMATION = "CONFIRMATION"
    RETRY = "RETRY"


class OperationType(StringEnum):
    STOCK_IN = "STOCK_IN"
    PERSONAL_USE = "PERSONAL_USE"
    PUBLIC_USE = "PUBLIC_USE"
    PERSONAL_RETURN = "PERSONAL_RETURN"
    PUBLIC_RETURN = "PUBLIC_RETURN"
    TRANSFER = "TRANSFER"
    REPAIR_START = "REPAIR_START"
    REPAIR_COMPLETE = "REPAIR_COMPLETE"
```

Import `ApprovalExecutionMode` in `models/workflow.py` and add:

```python
approval_execution_mode: Mapped[str] = mapped_column(
    String(32),
    nullable=False,
    default=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
    server_default=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
)
```

- [ ] **Step 5: Add revision 004**

Create `004_operation_contract_freeze.py`:

```python
"""freeze shared operation contracts

Revision ID: 004
Revises: 003
Create Date: 2026-07-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("operation_requests") as batch_op:
        batch_op.add_column(
            sa.Column(
                "approval_execution_mode",
                sa.String(length=32),
                nullable=False,
                server_default="AUTO_ON_APPROVAL",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("operation_requests") as batch_op:
        batch_op.drop_column("approval_execution_mode")
```

- [ ] **Step 6: Verify GREEN**

Run the three focused tests from Step 3. Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add back/app/enums/__init__.py back/app/models/workflow.py \
  back/migrations/versions/004_operation_contract_freeze.py \
  back/tests/test_operation_models.py back/tests/test_migrations.py
git commit -m "feat: persist operation execution mode"
```

### Task 2: Make request creation replay-safe and snapshot-complete

**Files:**

- Modify: `back/app/services/operation_service.py`
- Modify: `back/tests/test_asset_business_locks.py`
- Modify: `back/tests/test_operation_executor.py`

- [ ] **Step 1: Write failing creation and replay assertions**

Update creation tests to use a target mapping and result object:

```python
result = service.create_request(
    operation_type="TRANSFER",
    applicant_id=users[0].id,
    approval_channel=ApprovalChannel.INTERNAL.value,
    approval_execution_mode=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
    assets=list(reversed(assets)),
    target_data_by_asset_id={
        assets[0].id: {"location_id": 101},
        assets[1].id: {"location_id": 101},
    },
    idempotency_key="transfer-once",
)
assert result.created is True
operation = result.operation

replay = service.create_request(
    operation_type="TRANSFER",
    applicant_id=users[0].id,
    approval_channel=ApprovalChannel.INTERNAL.value,
    approval_execution_mode=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
    assets=assets,
    target_data_by_asset_id={
        assets[0].id: {"location_id": 101},
        assets[1].id: {"location_id": 101},
    },
    idempotency_key="transfer-once",
)
assert replay.created is False
assert replay.operation.id == operation.id
```

Add assertions that snapshots contain the corresponding target data.

- [ ] **Step 2: Add failing validation cases**

Add parameterized cases for missing target, extra target, and invalid JSON:

```python
@pytest.mark.parametrize(
    "target_data",
    [
        {},
        {-1: {"location_id": 1}},
        {"ASSET_ID": {"bad": object()}},
    ],
)
def test_create_request_rejects_invalid_target_snapshots(
    app, target_data
) -> None:
    organization, users, assets = _seed_assets("TARGET")
    if "ASSET_ID" in target_data:
        target_data = {assets[0].id: target_data["ASSET_ID"]}
    with pytest.raises(BusinessException):
        _operation_service().create_request(
            operation_type="TRANSFER",
            applicant_id=users[0].id,
            approval_channel=ApprovalChannel.INTERNAL.value,
            approval_execution_mode="AUTO_ON_APPROVAL",
            assets=[assets[0]],
            target_data_by_asset_id=target_data,
            idempotency_key=None,
        )
```

Replace the old mixed-organization rejection test with:

```python
result = _operation_service().create_request(
    operation_type="TRANSFER",
    applicant_id=users[0].id,
    approval_channel=ApprovalChannel.INTERNAL.value,
    approval_execution_mode="AUTO_ON_APPROVAL",
    assets=assets,
    target_data_by_asset_id={asset.id: {"location_id": asset.location_id} for asset in assets},
    idempotency_key=None,
)
assert result.created is True
assert {item.organization_id_snapshot for item in OperationRequestAsset.query.all()} == {
    asset.organization_id for asset in assets
}
```

- [ ] **Step 3: Run tests and verify RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_asset_business_locks.py -q
```

Expected: failures because `create_request()` returns a model, rejects mixed organizations, and writes `{}` target snapshots.

- [ ] **Step 4: Implement the immutable result and validation**

At the top of `operation_service.py` add `json`, `dataclass`, and `Mapping`, then implement:

```python
@dataclass(frozen=True)
class CreateOperationResult:
    operation: OperationRequest
    created: bool


def _validate_assets_and_targets(
    assets: list[Asset],
    target_data_by_asset_id: Mapping[int, Mapping[str, Any]],
) -> list[Asset]:
    if not assets:
        raise BusinessException("申请至少包含一项资产")
    ordered = sorted(assets, key=lambda asset: asset.id)
    asset_ids = [asset.id for asset in ordered]
    if any(asset_id is None for asset_id in asset_ids) or len(
        set(asset_ids)
    ) != len(asset_ids):
        raise BusinessException("申请包含重复或未保存的资产")
    if set(target_data_by_asset_id) != set(asset_ids):
        raise BusinessException("申请资产与目标快照不一致")
    for target in target_data_by_asset_id.values():
        try:
            json.dumps(dict(target), allow_nan=False)
        except (TypeError, ValueError) as error:
            raise BusinessException("资产目标快照不是有效 JSON") from error
    return ordered
```

Change `create_request()` to accept:

```python
approval_execution_mode: str,
assets: list[Asset],
target_data_by_asset_id: Mapping[int, Mapping[str, Any]],
```

Remove `organization_id`. Validate the execution mode against `ApprovalExecutionMode`; reject `DIRECT + MANUAL_CONFIRM`. Persist the mode and each `dict(target_data_by_asset_id[asset.id])`.

Expose the persisted mode in `_serialize()`:

```python
"approval_execution_mode": operation.approval_execution_mode,
```

Add the same assertion to request detail tests so future feature APIs can detect `MANUAL_CONFIRM` without importing models.

All existing/recovered branches return:

```python
return CreateOperationResult(operation=existing, created=False)
```

The new branch returns:

```python
return CreateOperationResult(operation=operation, created=True)
```

- [ ] **Step 5: Mechanically update all existing callers**

Use:

```bash
rg -n "create_request\(" back/app back/tests --glob '*.py'
```

For every call, remove `organization_id`, add `approval_execution_mode="AUTO_ON_APPROVAL"`, add a target mapping for every asset, and unwrap `.operation` when the caller needs the model. In concurrency tests return `result.operation.id`; assert `created` explicitly where replay behavior matters.

- [ ] **Step 6: Verify GREEN and concurrency replay**

```bash
cd back
.venv/bin/python -m pytest \
  tests/test_asset_business_locks.py \
  tests/test_operation_executor.py -q
```

Expected: PASS, including one request/one lock set under concurrent replay.

- [ ] **Step 7: Commit**

```bash
git add back/app/services/operation_service.py \
  back/tests/test_asset_business_locks.py back/tests/test_operation_executor.py
git commit -m "feat: freeze operation creation contract"
```

### Task 3: Add ordered row locks and allowlisted asset CAS

**Files:**

- Modify: `back/app/repositories/asset_repository.py`
- Create: `back/tests/test_asset_transition_contracts.py`

- [ ] **Step 1: Write failing repository tests**

Create this seed helper in the new test file:

```python
def _seed_transition_assets() -> list[Asset]:
    organization = Organization(code="TRANSITION-ORG", name="转换组织")
    unit = Unit(code="TRANSITION-UNIT", name="转换单位")
    source = AssetSource(code="TRANSITION-SOURCE", name="转换来源")
    location = AssetLocation(
        code="TRANSITION-LOCATION", name="转换地点", is_selectable=True
    )
    manager = User(username="transition-manager", password="x", enabled=True)
    db.session.add_all([organization, unit, source, location, manager])
    db.session.flush()
    category = AssetCategory(
        code="TRANSITION-CATEGORY",
        name="转换分类",
        service_life_months=12,
        default_unit_id=unit.id,
    )
    db.session.add(category)
    db.session.flush()
    assets = [
        Asset(
            asset_code=f"TRANSITION-ASSET-{index}",
            asset_name=f"转换资产{index}",
            status=AssetStatus.IDLE.value,
            organization_id=organization.id,
            category_id=category.id,
            unit_id=unit.id,
            original_amount=Decimal("1.00"),
            purchase_date=date(2026, 7, 21),
            manager_id=manager.id,
            source_id=source.id,
            location_id=location.id,
        )
        for index in (1, 2, 3, 4)
    ]
    db.session.add_all(assets)
    db.session.flush()
    return assets
```

Add the repository behavior test:

```python
def test_asset_repository_locks_in_id_order_and_updates_with_cas(app) -> None:
    assets = _seed_transition_assets()
    locked = asset_repository.find_many_for_update([assets[1].id, assets[0].id])
    assert [asset.id for asset in locked] == [assets[0].id, assets[1].id]

    assert asset_repository.cas_update(
        assets[0].id,
        assets[0].version,
        {"status": AssetStatus.IN_USE.value, "holder_user_id": assets[0].manager_id},
    ) is True
    db.session.flush()
    db.session.expire_all()
    updated = db.session.get(Asset, assets[0].id)
    assert updated is not None
    assert updated.status == AssetStatus.IN_USE.value
    assert updated.version == 2

    assert asset_repository.cas_update(
        updated.id,
        1,
        {"status": AssetStatus.REPAIRING.value},
    ) is False
```

Add an unsafe-field test:

```python
with pytest.raises(BusinessException, match="不允许更新"):
    asset_repository.cas_update(asset.id, asset.version, {"organization_id": 999})
```

- [ ] **Step 2: Run and verify RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_asset_transition_contracts.py -q
```

Expected: missing repository methods.

- [ ] **Step 3: Implement ordered queries and CAS**

Add imports for `Sequence`, `Mapping`, `update`, and `BusinessException`, then:

```python
_CAS_FIELDS = {
    "status",
    "usage_type",
    "holder_user_id",
    "public_object_id",
    "usage_department_id",
    "location_id",
}


def find_many_ordered(self, asset_ids: Sequence[int]) -> list[Asset]:
    ids = sorted(set(asset_ids))
    if not ids:
        return []
    stmt = select(Asset).where(Asset.id.in_(ids)).order_by(Asset.id.asc())
    return list(db.session.scalars(stmt).all())


def find_many_for_update(self, asset_ids: Sequence[int]) -> list[Asset]:
    ids = sorted(set(asset_ids))
    if not ids:
        return []
    stmt = (
        select(Asset)
        .where(Asset.id.in_(ids))
        .order_by(Asset.id.asc())
        .with_for_update()
    )
    return list(db.session.scalars(stmt).all())


def cas_update(
    self,
    asset_id: int,
    expected_version: int,
    changes: Mapping[str, object],
) -> bool:
    invalid = set(changes) - _CAS_FIELDS
    if invalid:
        raise BusinessException(f"资产字段不允许更新: {', '.join(sorted(invalid))}")
    if not changes:
        raise BusinessException("资产更新内容不能为空")
    statement = (
        update(Asset)
        .where(Asset.id == asset_id, Asset.version == expected_version)
        .values(**dict(changes), version=Asset.version + 1)
        .execution_options(synchronize_session=False)
    )
    result = db.session.execute(statement)
    return result.rowcount == 1
```

- [ ] **Step 4: Verify GREEN**

Run the test file from Step 2. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add back/app/repositories/asset_repository.py \
  back/tests/test_asset_transition_contracts.py
git commit -m "feat: add asset transition primitives"
```

### Task 4: Add one-level asset relation expansion

**Files:**

- Create: `back/app/services/asset_relation_service.py`
- Modify: `back/app/services/__init__.py`
- Modify: `back/app/repositories/asset_repository.py`
- Modify: `back/tests/test_asset_transition_contracts.py`

- [ ] **Step 1: Write failing relation tests**

Create a main asset, two direct children, and a standalone asset. Assert:

```python
expanded = asset_relation_service.expand_with_direct_children(
    [standalone.id, main.id, main.id]
)
assert [asset.id for asset in expanded] == sorted(
    [main.id, child_a.id, child_b.id, standalone.id]
)
```

Then attach a grandchild to `child_a` and assert:

```python
with pytest.raises(BusinessException, match="只允许一层"):
    asset_relation_service.expand_with_direct_children([main.id])
```

Also assert a missing requested ID raises a safe business error.

- [ ] **Step 2: Run and verify RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_asset_transition_contracts.py -q
```

Expected: relation service/module missing.

- [ ] **Step 3: Add the child query**

Add to `AssetRepository`:

```python
def find_direct_children(self, parent_ids: Sequence[int]) -> list[Asset]:
    ids = sorted(set(parent_ids))
    if not ids:
        return []
    stmt = (
        select(Asset)
        .where(Asset.parent_asset_id.in_(ids))
        .order_by(Asset.id.asc())
    )
    return list(db.session.scalars(stmt).all())
```

- [ ] **Step 4: Implement the service**

```python
"""Read-only one-level main/attachment asset expansion."""

from app.common import BusinessException, ResultCode
from app.models import Asset
from app.repositories.asset_repository import asset_repository


def expand_with_direct_children(asset_ids: list[int]) -> list[Asset]:
    requested_ids = sorted(set(asset_ids))
    roots = asset_repository.find_many_ordered(requested_ids)
    if len(roots) != len(requested_ids):
        raise BusinessException("资产不存在", result_code=ResultCode.NOT_FOUND)
    children = asset_repository.find_direct_children(requested_ids)
    grandchildren = asset_repository.find_direct_children(
        [asset.id for asset in children]
    )
    if grandchildren:
        raise BusinessException("主附资产只允许一层关系")
    unique_assets = {asset.id: asset for asset in [*roots, *children]}
    return sorted(unique_assets.values(), key=lambda asset: asset.id)


__all__ = ["expand_with_direct_children"]
```

Export the module from `app/services/__init__.py` without exporting extra symbols.

- [ ] **Step 5: Verify GREEN**

Run `tests/test_asset_transition_contracts.py`. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add back/app/repositories/asset_repository.py \
  back/app/services/asset_relation_service.py back/app/services/__init__.py \
  back/tests/test_asset_transition_contracts.py
git commit -m "feat: add asset relation expansion"
```

### Task 5: Add generic lifecycle and operation audit writers

**Files:**

- Modify: `back/app/services/audit_service.py`
- Modify: `back/tests/test_asset_transition_contracts.py`

- [ ] **Step 1: Write failing audit tests**

Using a seeded user, asset, and operation:

```python
audit_service.record_asset_lifecycle(
    asset_id=asset.id,
    operation_type="TRANSFER",
    request_no=operation.request_no,
    actor_id=user.id,
    before_data={"location_id": 1},
    after_data={"location_id": 2},
)
audit_service.record_operation(
    operation_request_id=operation.id,
    operation_type="TRANSFER",
    actor_id=user.id,
    before_data={"asset_ids": [asset.id]},
    after_data={"result": "SUCCESS"},
)

lifecycle = db.session.query(AssetLifecycleRecord).one()
log = db.session.query(OperationLog).one()
assert lifecycle.operation_type == "TRANSFER"
assert lifecycle.before_data == {"location_id": 1}
assert log.action == "TRANSFER"
assert log.resource_type == "operation_request"
assert log.resource_id == str(operation.id)
```

Retain an assertion that `record_asset_stock_in()` still writes its existing asset-scoped operation log.

- [ ] **Step 2: Run and verify RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_asset_transition_contracts.py -q
```

Expected: generic functions missing.

- [ ] **Step 3: Implement the writers**

```python
def record_asset_lifecycle(
    *,
    asset_id: int,
    operation_type: str,
    request_no: str,
    actor_id: int,
    before_data: Mapping[str, Any],
    after_data: Mapping[str, Any],
) -> None:
    asset_lifecycle_repository.add(
        AssetLifecycleRecord(
            asset_id=asset_id,
            operation_type=operation_type,
            operation_no=request_no,
            operator_id=actor_id,
            before_data=dict(before_data),
            after_data=dict(after_data),
        )
    )


def record_operation(
    *,
    operation_request_id: int,
    operation_type: str,
    actor_id: int,
    before_data: Mapping[str, Any] | None,
    after_data: Mapping[str, Any] | None,
) -> None:
    operation_log_repository.add(
        OperationLog(
            action=operation_type,
            resource_type="operation_request",
            resource_id=str(operation_request_id),
            operator_id=actor_id,
            before_data=dict(before_data) if before_data is not None else None,
            after_data=dict(after_data) if after_data is not None else None,
        )
    )
```

Refactor only the lifecycle part of `record_asset_stock_in()` through `record_asset_lifecycle()`; preserve its current asset-scoped `OperationLog` exactly.

- [ ] **Step 4: Verify GREEN and stock-in compatibility**

```bash
cd back
.venv/bin/python -m pytest \
  tests/test_asset_transition_contracts.py \
  tests/test_assets.py \
  tests/test_stock_in_e2e.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add back/app/services/audit_service.py \
  back/tests/test_asset_transition_contracts.py
git commit -m "feat: add shared asset audit writers"
```

### Task 6: Enforce the execution trigger/mode matrix

**Files:**

- Modify: `back/app/services/operation_executor.py`
- Modify: `back/tests/test_operation_executor.py`

- [ ] **Step 1: Write failing AUTO and MANUAL tests**

Parameterize the operation seed with `approval_execution_mode`. Add:

```python
def test_manual_confirmation_waits_then_executes_once(app) -> None:
    actor, _asset, operation = _seed_approved_operation(
        approval_execution_mode="MANUAL_CONFIRM"
    )
    handler = StubHandler()
    _registry().clear()
    _registry().register(handler)

    waiting = _executor().execute_after_approval(operation.id, actor.id)
    assert waiting.execution_status == ExecutionStatus.NOT_STARTED.value
    assert db.session.query(OperationExecutionAttempt).count() == 0
    assert db.session.query(AssetBusinessLock).count() == 1

    completed = _executor().confirm(operation.id, actor.id)
    assert completed.execution_status == ExecutionStatus.SUCCESS.value
    assert handler.executions == 1
    assert db.session.query(AssetBusinessLock).count() == 0
```

Add illegal-combination assertions:

```python
with pytest.raises(BusinessException):
    _executor().execute(operation.id, actor.id, ExecutionTriggerType.APPROVAL.value)
assert db.session.query(OperationExecutionAttempt).count() == 0
```

Use the inverse case for `AUTO_ON_APPROVAL + CONFIRMATION`.

- [ ] **Step 2: Run and verify RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_operation_executor.py -q
```

Expected: missing dispatch/confirm functions and no mode validation.

- [ ] **Step 3: Implement the matrix before attempt creation**

Add:

```python
def _validate_trigger(operation: OperationRequest, trigger_type: str) -> None:
    if trigger_type == ExecutionTriggerType.APPROVAL.value and (
        operation.approval_execution_mode
        != ApprovalExecutionMode.AUTO_ON_APPROVAL.value
    ):
        raise BusinessException(
            "当前申请需要人工确认后执行", result_code=ResultCode.BAD_REQUEST
        )
    if trigger_type == ExecutionTriggerType.CONFIRMATION.value and (
        operation.approval_execution_mode
        != ApprovalExecutionMode.MANUAL_CONFIRM.value
    ):
        raise BusinessException(
            "当前申请不能由人工确认触发", result_code=ResultCode.BAD_REQUEST
        )
```

Call it after approval-status and success-idempotency checks, but before creating an execution attempt. Treat `CONFIRMATION` like `APPROVAL`: execution must be `NOT_STARTED`. Keep `RETRY` restricted to `FAILED`.

Add:

```python
def execute_after_approval(
    operation_request_id: int, actor_id: int
) -> OperationRequest:
    operation = _require_operation(operation_request_id)
    if (
        operation.approval_execution_mode
        == ApprovalExecutionMode.MANUAL_CONFIRM.value
    ):
        return operation
    return execute(
        operation_request_id, actor_id, ExecutionTriggerType.APPROVAL.value
    )


def confirm(operation_request_id: int, actor_id: int) -> OperationRequest:
    return execute(
        operation_request_id, actor_id, ExecutionTriggerType.CONFIRMATION.value
    )
```

Export both functions.

- [ ] **Step 4: Verify GREEN and failure/retry behavior**

```bash
cd back
.venv/bin/python -m pytest tests/test_operation_executor.py -q
```

Expected: PASS; failed execution still retains locks and retry still works.

- [ ] **Step 5: Commit**

```bash
git add back/app/services/operation_executor.py \
  back/tests/test_operation_executor.py
git commit -m "feat: support manual operation confirmation"
```

### Task 7: Route every approval completion through one dispatcher

**Files:**

- Modify: `back/app/services/approval_provider_service.py`
- Modify: `back/app/services/operation_service.py`
- Modify: `back/app/services/stock_in_service.py`
- Modify: `back/tests/test_approval_providers.py`
- Modify: `back/tests/test_operation_api.py`
- Modify: `back/tests/test_stock_in_e2e.py`

- [ ] **Step 1: Write a failing FEISHU manual-confirm test**

Extend `_operation()` to accept an execution mode and add:

```python
manual = _operation(
    actor,
    ApprovalChannel.FEISHU.value,
    "PROVIDER-MANUAL",
    approval_execution_mode="MANUAL_CONFIRM",
)
service.submit(manual.id, actor.id)
approved = service.handle_callback(
    provider="FEISHU",
    external_event_id="manual-approved",
    external_instance_id=manual.external_instance_id,
    status="APPROVED",
    actor_id=actor.id,
)
assert approved.approval_status == ApprovalStatus.APPROVED.value
assert approved.execution_status == ExecutionStatus.NOT_STARTED.value
assert db.session.query(OperationExecutionAttempt).count() == 0
```

- [ ] **Step 2: Write failing internal and DIRECT routing tests**

In `test_operation_api.py`, add an `approval_execution_mode` argument to `_seed_api_context()` and pass it into `OperationRequest`. Then add:

```python
def test_internal_manual_confirmation_waits_for_feature_acceptance(client) -> None:
    context = _seed_api_context(
        client, approval_execution_mode="MANUAL_CONFIRM"
    )
    operation_handler_registry.clear()
    operation_handler_registry.register(ApiNoopHandler())

    approved = client.post(
        f"/api/v1/approval-tasks/{context['task'].id}/approve",
        headers=context["approver_headers"],
        json={"opinion": "同意"},
    ).get_json()["data"]

    assert approved["approval_status"] == ApprovalStatus.APPROVED.value
    assert approved["execution_status"] == ExecutionStatus.NOT_STARTED.value
    assert db.session.query(OperationExecutionAttempt).count() == 0
```

In `test_approval_providers.py`, keep the existing DIRECT test for AUTO and add:

```python
manual_direct = _operation(
    actor,
    ApprovalChannel.DIRECT.value,
    "PROVIDER-DIRECT-MANUAL",
    approval_execution_mode="MANUAL_CONFIRM",
)
with pytest.raises(BusinessException, match="人工确认"):
    service.confirm_direct(manual_direct.id, actor.id)
```

- [ ] **Step 3: Run and verify RED**

```bash
cd back
.venv/bin/python -m pytest \
  tests/test_approval_providers.py \
  tests/test_operation_api.py -q
```

Expected: FEISHU and INTERNAL still execute immediately; DIRECT does not reject manual mode.

- [ ] **Step 4: Replace all approval-triggered direct executor calls**

Apply these exact replacements:

```python
# approval_provider_service.handle_callback / confirm_direct
return operation_executor.execute_after_approval(operation.id, actor_id)

# operation_service.approve_task
if outcome.request_approved:
    operation = operation_executor.execute_after_approval(operation.id, actor_id)

# stock_in_service.approve
if outcome.request_approved:
    operation = operation_executor.execute_after_approval(operation.id, actor_id)
```

Before changing a DIRECT operation to APPROVED, `confirm_direct()` must reject `MANUAL_CONFIRM` with `BusinessException(ResultCode.BAD_REQUEST)`. Do not add another execution-mode branch elsewhere.

- [ ] **Step 5: Verify GREEN and stock-in AUTO compatibility**

```bash
cd back
.venv/bin/python -m pytest \
  tests/test_approval_providers.py \
  tests/test_operation_api.py \
  tests/test_stock_in_approval.py \
  tests/test_stock_in_e2e.py -q
```

Expected: PASS. Existing stock-in approval still executes immediately.

- [ ] **Step 6: Search for bypasses**

```bash
rg -n "execute\([^\n]*APPROVAL|ExecutionTriggerType\.APPROVAL" back/app --glob '*.py'
```

Expected: approval callers use `execute_after_approval`; only `operation_executor.py` directly constructs the approval trigger.

- [ ] **Step 7: Commit**

```bash
git add back/app/services/approval_provider_service.py \
  back/app/services/operation_service.py back/app/services/stock_in_service.py \
  back/tests/test_approval_providers.py back/tests/test_operation_api.py \
  back/tests/test_stock_in_e2e.py
git commit -m "refactor: centralize approval execution dispatch"
```

### Task 8: Verify migrations, compatibility, and independent review

**Files:**

- Modify only if a test exposes a contract defect in files already listed above.

- [ ] **Step 1: Run focused contract tests**

```bash
cd back
.venv/bin/python -m pytest \
  tests/test_operation_models.py \
  tests/test_asset_business_locks.py \
  tests/test_asset_transition_contracts.py \
  tests/test_operation_executor.py \
  tests/test_approval_providers.py \
  tests/test_operation_api.py \
  tests/test_migrations.py -q
```

Expected: all focused tests pass.

- [ ] **Step 2: Verify revision 004 upgrade and downgrade on a clean SQLite database**

The migration tests must execute:

```text
003 -> 004: approval_execution_mode exists and old rows read AUTO_ON_APPROVAL
004 -> 003: approval_execution_mode is removed and all pre-existing operation data remains
base -> 004: complete clean upgrade succeeds
```

Run:

```bash
cd back
.venv/bin/python -m pytest tests/test_migrations.py -q
```

Expected: PASS with no multiple-head warning.

- [ ] **Step 3: Run the complete backend gate**

```bash
cd back
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app/ config.py config_bootstrap.py
.venv/bin/python -m pytest -q
cd ..
git diff --check
bash scripts/guard-conventions.sh
```

Expected: every command exits 0.

- [ ] **Step 4: Run the independent six-dimensional review**

Start an independent read-only review agent. It must not edit files and must verify:

1. Requirements completeness against `2026-07-20-operation-contract-freeze-design.md`.
2. Logic correctness of replay, execution mode, CAS, relations, and audit.
3. Boundary cases: concurrent idempotency, mixed organizations, invalid JSON, stale versions, duplicate callbacks, waiting confirmation, multi-level relations, migration downgrade.
4. Code quality and adherence to Blueprint/service/repository boundaries.
5. Test coverage, including RED/GREEN evidence and stock-in compatibility.
6. Actual execution of focused tests, full gates, and migration commands.

The reviewer returns `PASS` or a severity-ranked fix list. The main thread applies fixes with a new failing test first, then sends the same reviewer for re-verification. Repeat until `PASS` or a concrete external blocker is documented.

- [ ] **Step 5: Commit review-driven fixes when the reviewer returns findings**

```bash
git add -p
git commit -m "fix: address operation contract review"
```

When the reviewer returns PASS without findings, do not create an empty commit.

- [ ] **Step 6: Push the contract-freeze branch**

```bash
git push -u origin feature/operation-contract-freeze
```

- [ ] **Step 7: Create the parallel feature worktrees only after PASS**

From the reviewed contract-freeze commit create:

```bash
git worktree add ../asset-system-usage-return -b feature/asset-usage-return
git worktree add ../asset-system-transfer -b feature/asset-transfer
git worktree add ../asset-system-repair -b feature/asset-repair
```

Do not create these branches from `main` or `feature/backend-foundation-v2`; all three must share the exact reviewed contract-freeze commit.
