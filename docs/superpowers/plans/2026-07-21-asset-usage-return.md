# Asset Usage and Return Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build personal/public asset usage and return flows on the frozen operation kernel, including local Feishu simulation, one-level main/attachment expansion, manual return inspection, idempotency, audit, and API coverage.

**Architecture:** Add only feature leaf modules on this branch. Feature services create common `OperationRequest` aggregates, handlers apply immutable target snapshots through the common executor and CAS repository, and feature repositories own detail persistence and filtered queries. Public registrations, permission seeds, and migration `005_parallel_operation_features.py` remain a post-merge integration task.

**Tech Stack:** Python 3.13, Flask 3, Flask-JWT-Extended, SQLAlchemy 2, Marshmallow, pytest, Ruff, mypy, SQLite tests, external MySQL deployment.

---

## Branch and file boundary

Work in `/Users/chaoslin/Project/asset-system/.worktrees/asset-usage-return-v2` on `feature/asset-usage-return-v2`.

Do not modify public aggregation, operation-kernel, permission seed, config, or migration files on this branch. In particular, do not modify:

```text
back/app/enums/__init__.py
back/app/models/__init__.py
back/app/repositories/__init__.py
back/app/services/__init__.py
back/app/api/__init__.py
back/app/operations/__init__.py
back/app/operations/registry.py
back/app/__init__.py
back/migrations/versions/*
```

Create these focused modules:

```text
back/app/models/asset_usage_return.py
back/app/repositories/asset_usage_return_repository.py
back/app/schemas/asset_usage_return.py
back/app/services/asset_usage_return_support.py
back/app/services/asset_usage_service.py
back/app/services/asset_return_service.py
back/app/services/local_feishu_service.py
back/app/operations/asset_usage_return_handlers.py
back/app/api/asset_usage.py
back/app/api/asset_returns.py
back/app/api/local_feishu.py
back/tests/asset_usage_return_fixtures.py
back/tests/test_asset_usage_return_models.py
back/tests/test_asset_usage_return_schemas.py
back/tests/test_asset_usage_service.py
back/tests/test_asset_return_service.py
back/tests/test_asset_usage_return_api.py
back/tests/test_asset_usage_return_concurrency.py
```

## Task 1: Feature models and repositories

**Files:**

- Create: `back/app/models/asset_usage_return.py`
- Create: `back/app/repositories/asset_usage_return_repository.py`
- Create: `back/tests/test_asset_usage_return_models.py`

- [ ] **Step 1: Write failing model contract tests**

Import the leaf model directly so metadata registration does not require changing `app.models.__init__`:

```python
from app.models.asset_usage_return import (
    AssetReturnItem,
    AssetReturnRequest,
    AssetUsageRequest,
)


def test_usage_and_return_models_expose_required_constraints(app) -> None:
    assert AssetUsageRequest.__table__.name == "asset_usage_requests"
    assert AssetUsageRequest.__table__.c.operation_request_id.unique is True
    assert AssetReturnRequest.__table__.c.operation_request_id.unique is True
    assert AssetReturnItem.__table__.c.operation_request_asset_id.unique is True
    assert AssetReturnItem.__table__.c.condition.nullable is True
```

Add a repository test that seeds one operation, two `OperationRequestAsset` rows, and two return items in reverse insertion order, then asserts `find_by_operation()` returns their request-asset IDs ascending.

- [ ] **Step 2: Run the tests and verify RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_asset_usage_return_models.py -q
```

Expected: collection fails with `ModuleNotFoundError: app.models.asset_usage_return`.

- [ ] **Step 3: Implement the leaf models**

Use this public shape with `TimestampMixin`, indexed foreign keys, `Mapped`, and existing SQLAlchemy typing conventions:

```python
class AssetUsageRequest(TimestampMixin, db.Model):
    __tablename__ = "asset_usage_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_id: Mapped[int] = mapped_column(
        ForeignKey("operation_requests.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    target_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True,
    )
    target_public_object_id: Mapped[int | None] = mapped_column(
        ForeignKey("public_usage_objects.id", ondelete="RESTRICT"),
        nullable=True, index=True,
    )
    usage_department_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True, index=True,
    )
    target_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("asset_locations.id", ondelete="RESTRICT"), nullable=True, index=True,
    )


class AssetReturnRequest(TimestampMixin, db.Model):
    __tablename__ = "asset_return_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_id: Mapped[int] = mapped_column(
        ForeignKey("operation_requests.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    return_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("asset_locations.id", ondelete="RESTRICT"), nullable=True, index=True,
    )
    confirmed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )


class AssetReturnItem(TimestampMixin, db.Model):
    __tablename__ = "asset_return_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_asset_id: Mapped[int] = mapped_column(
        ForeignKey("operation_request_assets.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    condition: Mapped[str | None] = mapped_column(String(16), nullable=True)
    condition_description: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Reference `operation_requests`, `operation_request_assets`, `users`, `organizations`, `public_usage_objects`, and `asset_locations`. Use `String(16)` for condition and `Text` for description.

- [ ] **Step 4: Implement feature repositories**

Provide these interfaces and leaf-module singleton instances:

```python
class AssetUsageRequestRepository(BaseRepository[AssetUsageRequest]):
    def find_by_operation(self, operation_request_id: int) -> AssetUsageRequest | None:
        return self.find_one(
            AssetUsageRequest.operation_request_id == operation_request_id
        )


class AssetReturnRequestRepository(BaseRepository[AssetReturnRequest]):
    def find_by_operation(self, operation_request_id: int) -> AssetReturnRequest | None:
        return self.find_one(
            AssetReturnRequest.operation_request_id == operation_request_id
        )


class AssetReturnItemRepository(BaseRepository[AssetReturnItem]):
    def find_by_operation(self, operation_request_id: int) -> list[AssetReturnItem]:
        statement = (
            select(AssetReturnItem)
            .join(
                OperationRequestAsset,
                OperationRequestAsset.id == AssetReturnItem.operation_request_asset_id,
            )
            .where(OperationRequestAsset.operation_request_id == operation_request_id)
            .order_by(AssetReturnItem.operation_request_asset_id.asc())
        )
        return list(db.session.scalars(statement).all())

    def find_by_request_asset_ids(
        self, ids: Sequence[int]
    ) -> list[AssetReturnItem]:
        ordered_ids = sorted(set(ids))
        if not ordered_ids:
            return []
        statement = (
            select(AssetReturnItem)
            .where(AssetReturnItem.operation_request_asset_id.in_(ordered_ids))
            .order_by(AssetReturnItem.operation_request_asset_id.asc())
        )
        return list(db.session.scalars(statement).all())
```

Repositories never commit and never raise `BusinessException`.

- [ ] **Step 5: Verify and commit**

```bash
.venv/bin/python -m pytest tests/test_asset_usage_return_models.py tests/test_operation_models.py -q
git add app/models/asset_usage_return.py \
  app/repositories/asset_usage_return_repository.py \
  tests/test_asset_usage_return_models.py
git commit -m "feat: add usage return persistence"
```

Expected: tests pass and the commit contains only the three task files.

## Task 2: Schemas and shared validation

**Files:**

- Create: `back/app/schemas/asset_usage_return.py`
- Create: `back/app/services/asset_usage_return_support.py`
- Create: `back/tests/asset_usage_return_fixtures.py`
- Create: `back/tests/test_asset_usage_return_schemas.py`

- [ ] **Step 1: Add reusable seed builders**

```python
@dataclass(frozen=True)
class UsageReturnContext:
    organization: Organization
    location: AssetLocation
    return_location: AssetLocation
    manager: User
    employee: User
    public_object: PublicUsageObject
    main_asset: Asset
    child_asset: Asset


def grant_permissions(user: User, *permission_codes: str) -> None:
    role = Role(
        code=f"ROLE-{user.username}",
        name=f"Role for {user.username}",
        data_scope=DataScope.ALL.value,
    )
    db.session.add(role)
    db.session.flush()
    for code in permission_codes:
        permission = Permission(code=code, name=code, module="asset")
        db.session.add(permission)
        db.session.flush()
        db.session.add(
            RolePermission(role_id=role.id, permission_id=permission.id)
        )
    db.session.add(UserRole(user_id=user.id, role_id=role.id))


def register_usage_return_handlers() -> None:
    handlers = (
        PersonalUsageHandler(),
        PublicUsageHandler(),
        PersonalReturnHandler(),
        PublicReturnHandler(),
    )
    for handler in handlers:
        if not operation_handler_registry.contains(handler.operation_type):
            operation_handler_registry.register(handler)
```

Implement `seed_usage_return_context()` with concrete codes prefixed `UR-`: one enabled organization, two selectable locations, one unit, one source, one category, enabled manager and employee users in that organization, one enabled public object, an idle main asset, and an idle child whose `parent_asset_id` is the main ID. Flush before constructing dependent rows and return the dataclass above.

- [ ] **Step 2: Write failing schema tests**

Use this representative validation pattern for every schema:

```python
def test_damaged_inspection_requires_description() -> None:
    schema = ReturnInspectionSchema()
    with pytest.raises(ValidationError) as captured:
        schema.load({"asset_id": 1, "condition": "DAMAGED"})
    assert "condition_description" in captured.value.messages


def test_normal_inspection_discards_blank_description() -> None:
    loaded = ReturnInspectionSchema().load(
        {"asset_id": 1, "condition": "NORMAL", "condition_description": "  "}
    )
    assert loaded["condition_description"] is None


def test_page_query_caps_size_at_one_hundred() -> None:
    with pytest.raises(ValidationError):
        UsageReturnPageQuerySchema().load({"size": 101})
```

Add the same concrete `schema.load()` assertions for missing personal target, missing public location/object, duplicate confirmation asset IDs, unexpected holder field in personal return, and reject action without reason/event key.

- [ ] **Step 3: Run schema tests and verify RED**

```bash
.venv/bin/python -m pytest tests/test_asset_usage_return_schemas.py -q
```

Expected: collection fails because `app.schemas.asset_usage_return` does not exist.

- [ ] **Step 4: Implement schemas**

Create:

Define a private `_AssetIdsSchema` containing `asset_ids` and `idempotency_key`. Derive `PersonalUsageCreateSchema`, `PublicUsageCreateSchema`, and `PersonalReturnCreateSchema`; add their required integer fields. Define `ReturnInspectionSchema` with a `@validates_schema` method that strips descriptions and enforces damaged/normal rules. Define public return and confirm schemas with a 1–100 nested inspection list plus a schema-level duplicate-asset check. Define page and mock action schemas with the exact ranges and choices below.

Rules: `asset_ids` has 1–100 strict integers; keys have 1–191 characters; condition is `NORMAL` or `DAMAGED`; description is at most 2000 characters; damaged requires a nonblank description; normal normalizes it to `None`; mock action is `APPROVE`, `REJECT`, or `WITHDRAW`; only reject requires reason; page is nonnegative and size is 1–100.

- [ ] **Step 5: Write failing support tests**

Use concrete seed mutations and assertions. For example:

```python
def test_expansion_adds_children_and_rejects_child_only(app) -> None:
    context = seed_usage_return_context()
    expanded = support.expand_assets([context.main_asset.id])
    assert [item.id for item in expanded] == sorted(
        [context.main_asset.id, context.child_asset.id]
    )
    with pytest.raises(BusinessException, match="先解除主附关系"):
        support.expand_assets([context.child_asset.id])
```

Add equivalent tests that move the child to another organization, mix idle/in-use assets, disable or detach the employee organization, disable the public object, disable the location, and mark the location nonselectable.

- [ ] **Step 6: Implement support functions**

Use this exact expansion implementation and focused validators with one condition each:

```python
def expand_assets(asset_ids: Sequence[int]) -> list[Asset]:
    requested = set(asset_ids)
    assets = asset_relation_service.expand_with_direct_children(asset_ids)
    if any(
        asset.id in requested
        and asset.parent_asset_id is not None
        and asset.parent_asset_id not in requested
        for asset in assets
    ):
        raise BusinessException("附属资产单独操作前必须先解除主附关系")
    return assets


def require_assets_in_scope(actor_id: int, assets: Sequence[Asset]) -> None:
    for asset in assets:
        permission_service.require_organization_scope(
            actor_id, asset.organization_id
        )


def require_idle_assets(assets: Sequence[Asset]) -> None:
    if any(asset.status != AssetStatus.IDLE.value for asset in assets):
        raise BusinessException("只有闲置资产可以投入使用")
```

Implement `require_personal_assets()` as one `all()` predicate over `IN_USE/PERSONAL/holder_user_id`; `require_public_assets()` over `IN_USE/PUBLIC/public_object_id is not None`; target lookups through `rbac_repository` and `db.session.get(PublicUsageObject, id)`; location through the public master-data Service; request assets through `operation_request_asset_repository.find_by_request()`. `serialize_operation()` directly builds a dict from the already-authorized `OperationRequest`, common request-asset snapshots, and feature rows. It must not call `operation_service.get_request()`, because that common endpoint requires an unrelated `operation:request:view` permission.

`expand_assets()` calls the common one-level expansion and rejects a requested attached asset whose parent was not requested. Scope validation checks every expanded asset. Personal target requires an enabled user with `organization_id`; public target requires `RecordStatus.ENABLED`; location delegates to `master_data_service.require_selectable_location()`.

- [ ] **Step 7: Verify and commit**

```bash
.venv/bin/python -m pytest tests/test_asset_usage_return_schemas.py -q
.venv/bin/ruff check app/schemas/asset_usage_return.py \
  app/services/asset_usage_return_support.py \
  tests/asset_usage_return_fixtures.py \
  tests/test_asset_usage_return_schemas.py
.venv/bin/mypy app/schemas/asset_usage_return.py app/services/asset_usage_return_support.py
git add app/schemas/asset_usage_return.py \
  app/services/asset_usage_return_support.py \
  tests/asset_usage_return_fixtures.py \
  tests/test_asset_usage_return_schemas.py
git commit -m "feat: validate usage return requests"
```

Expected: tests, Ruff, and mypy pass.

## Task 3: Personal and public usage flows

**Files:**

- Create: `back/app/services/asset_usage_service.py`
- Create: `back/app/operations/asset_usage_return_handlers.py`
- Create: `back/tests/test_asset_usage_service.py`
- Modify: `back/tests/asset_usage_return_fixtures.py`

- [ ] **Step 1: Write failing personal usage tests**

Use this first end-to-end Service test, then clone its setup for replay, invalid-state, approval, and rejection cases:

```python
def test_submit_personal_usage_locks_main_and_child_and_submits_feishu(app) -> None:
    context = seed_usage_return_context()
    grant_permissions(context.manager, "asset:usage:manage")
    db.session.commit()
    result = asset_usage_service.submit_personal(
        {
            "asset_ids": [context.main_asset.id],
            "target_user_id": context.employee.id,
            "idempotency_key": "personal-use-1",
        },
        context.manager.id,
    )
    assert result["operation_type"] == OperationType.PERSONAL_USE.value
    assert result["external_instance_id"] == f"LOCAL-FEISHU-{result['id']}"
    assert db.session.query(OperationRequestAsset).count() == 2
    assert db.session.query(AssetBusinessLock).count() == 2
```

Replay calls the method twice and asserts one operation/detail/lock set. Invalid-state changes the child status and asserts zero operation rows. Approval registers handlers, invokes the provider callback, then asserts both assets, two lifecycles, one operation log, and one attempt. Rejection invokes a rejected callback and asserts original asset values and zero locks.

Assert `PERSONAL_USE`, `FEISHU/AUTO_ON_APPROVAL`, two snapshots, two locks, `LOCAL-FEISHU-{id}`, employee department, and retained per-asset location when omitted.

After personal submission works, add `seed_pending_personal_usage()` to the fixture module. It seeds context, grants manager permission, submits with idempotency key `fixture-personal-use`, and returns `(context, operation_request_repository.get(result["id"]))` after asserting the operation is present.

- [ ] **Step 2: Run personal tests and verify RED**

```bash
.venv/bin/python -m pytest tests/test_asset_usage_service.py -k personal -q
```

Expected: import fails for `asset_usage_service`.

- [ ] **Step 3: Implement personal submission**

```python
def submit_personal(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "asset:usage:manage")
    assets = support.expand_assets(payload["asset_ids"])
    support.require_assets_in_scope(actor_id, assets)
    support.require_idle_assets(assets)
    target_user = support.require_personal_target(payload["target_user_id"])
    targets = {
        asset.id: {
            "status": AssetStatus.IN_USE.value,
            "usage_type": UsageType.PERSONAL.value,
            "holder_user_id": target_user.id,
            "public_object_id": None,
            "usage_department_id": target_user.organization_id,
            "location_id": payload.get("location_id") or asset.location_id,
        }
        for asset in assets
    }
    # create common request, add AssetUsageRequest, submit FEISHU, serialize
```

Check common idempotency before mutable validation. Do not commit before provider submission; the provider transaction persists request, snapshots, feature detail, and locks together.

- [ ] **Step 4: Implement usage handlers**

```python
class PersonalUsageHandler:
    operation_type = OperationType.PERSONAL_USE.value
    safe_error_message = "个人领用执行失败，请联系管理员或稍后重试"


class PublicUsageHandler:
    operation_type = OperationType.PUBLIC_USE.value
    safe_error_message = "公共资产投入执行失败，请联系管理员或稍后重试"
```

Shared private helpers lock current assets in ID order, revalidate status/version, CAS each snapshot target, write one lifecycle per asset, then one request-scoped operation log. Any failed CAS raises `BusinessException("资产版本冲突")` so the common executor rolls back the batch.

- [ ] **Step 5: Write failing public usage tests**

```python
def test_submit_public_usage_directly_executes_main_and_child(app) -> None:
    context = seed_usage_return_context()
    grant_permissions(context.manager, "asset:usage:manage")
    register_usage_return_handlers()
    db.session.commit()
    result = asset_usage_service.submit_public(
        {
            "asset_ids": [context.main_asset.id],
            "public_object_id": context.public_object.id,
            "location_id": context.location.id,
            "idempotency_key": "public-use-1",
        },
        context.manager.id,
    )
    assert result["approval_status"] == ApprovalStatus.APPROVED.value
    assert result["execution_status"] == ExecutionStatus.SUCCESS.value
    assert db.session.query(AssetLifecycleRecord).count() == 2
    assert db.session.query(OperationLog).count() == 1
```

The validation test separately disables the public object and location. The replay test repeats the same idempotency key and asserts one operation, one attempt, two lifecycle rows, and one operation log.

Assert immediate `APPROVED/SUCCESS`, `IN_USE/PUBLIC`, public object/location, cleared holder/department, two lifecycle rows, one operation log, and no lock.

- [ ] **Step 6: Implement public submission**

Implement `submit_public(payload, actor_id)` with the same ordered structure as `submit_personal`: permission, idempotency replay, expansion, scope, state validation, public object/location validation, target map, common request, feature detail, `confirm_direct`, serialization.

Require `asset:usage:manage`, expansion, full scope, idle assets, enabled public object, and selectable location. Create `PUBLIC_USE` with `DIRECT/AUTO_ON_APPROVAL`, save detail, and call `approval_provider_service.confirm_direct()`.

- [ ] **Step 7: Verify and commit**

```bash
.venv/bin/python -m pytest tests/test_asset_usage_service.py \
  tests/test_operation_executor.py tests/test_approval_providers.py \
  tests/test_asset_transition_contracts.py -q
git add app/services/asset_usage_service.py \
  app/operations/asset_usage_return_handlers.py \
  tests/test_asset_usage_service.py
git commit -m "feat: implement asset usage flows"
```

Expected: all targeted and regression tests pass.

## Task 4: Personal and public return flows

**Files:**

- Create: `back/app/services/asset_return_service.py`
- Modify: `back/app/operations/asset_usage_return_handlers.py`
- Create: `back/tests/test_asset_return_service.py`
- Modify: `back/tests/asset_usage_return_fixtures.py`

- [ ] **Step 1: Write failing personal return tests**

```python
def test_employee_submits_only_owned_personal_assets(app) -> None:
    context = seed_usage_return_context()
    grant_permissions(context.employee, "asset:return:self")
    for asset in (context.main_asset, context.child_asset):
        asset.status = AssetStatus.IN_USE.value
        asset.usage_type = UsageType.PERSONAL.value
        asset.holder_user_id = context.employee.id
        asset.usage_department_id = context.employee.organization_id
    db.session.commit()
    result = asset_return_service.submit_personal(
        {"asset_ids": [context.main_asset.id], "idempotency_key": "return-1"},
        context.employee.id,
    )
    assert result["approval_execution_mode"] == "MANUAL_CONFIRM"
    assert db.session.query(AssetBusinessLock).count() == 2
```

The other-holder, public, and idle cases mutate exactly one child and assert zero request rows. The approval-waiting case registers handlers, sends `APPROVED`, and asserts `NOT_STARTED`, zero attempts, and two locks.

Assert `FEISHU/MANUAL_CONFIRM`, target snapshot clears usage fields but omits location, approval leaves `NOT_STARTED`, zero attempts, and locks remain.

- [ ] **Step 2: Run personal return tests and verify RED**

```bash
.venv/bin/python -m pytest tests/test_asset_return_service.py -k personal -q
```

Expected: import fails for `asset_return_service`.

- [ ] **Step 3: Implement personal return submission**

```python
def submit_personal(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "asset:return:self")
    assets = support.expand_assets(payload["asset_ids"])
    support.require_personal_assets(assets, actor_id)
    # create PERSONAL_RETURN with FEISHU/MANUAL_CONFIRM
    # add AssetReturnRequest and empty AssetReturnItem rows
    # submit provider and serialize
```

Employee ownership is stronger than organization scope for this self-service action, but every expanded child must have the same holder.

- [ ] **Step 4: Write failing inspection tests**

```python
def test_admin_confirms_return_with_complete_inspection_and_location(app) -> None:
    context, operation = seed_approved_personal_return()
    grant_permissions(context.manager, "asset:usage:manage")
    register_usage_return_handlers()
    db.session.commit()
    payload = {
        "return_location_id": context.return_location.id,
        "idempotency_key": "confirm-1",
        "items": [
            {"asset_id": context.main_asset.id, "condition": "NORMAL"},
            {"asset_id": context.child_asset.id, "condition": "DAMAGED",
             "condition_description": "screen cracked"},
        ],
    }
    result = asset_return_service.confirm(operation.id, payload, context.manager.id)
    assert result["execution_status"] == ExecutionStatus.SUCCESS.value
    assert db.session.query(AssetLifecycleRecord).count() == 2
    assert db.session.query(OperationExecutionAttempt).count() == 1
```

Before-approval and missing-item tests assert `BusinessException` and unchanged detail rows. Damage assertions inspect lifecycle metadata and idle asset state. Idempotency calls confirm twice and asserts one action claim, one attempt, two lifecycle rows, and one log.

- [ ] **Step 5: Implement inspection confirmation and handlers**

Expose `confirm(operation_request_id, payload, actor_id) -> dict[str, Any]` and keep it as the only Service method allowed to fill personal-return inspection fields.

Require `asset:usage:manage`, full snapshot scope, `APPROVED/NOT_STARTED/MANUAL_CONFIRM`, durable `RETURN_CONFIRM` action claim, exact inspection asset equality, and selectable location. The claim helper inserts `OperationActionIdempotency(status="PROCESSING")`, catches only the named unique-key conflict, rolls back, reloads the existing key, returns a completed result for replay, and reports "请求正在处理中" for a processing replay. Fill request/item rows, persist the action claim, call `operation_executor.confirm()`, then mark the claim completed even when the executor returns a persisted `FAILED` operation.

Return handlers overlay confirmed location onto:

```python
{
    "status": AssetStatus.IDLE.value,
    "usage_type": None,
    "holder_user_id": None,
    "public_object_id": None,
    "usage_department_id": None,
    "location_id": return_request.return_location_id,
}
```

Add condition metadata to lifecycle `after_data`, but never pass metadata keys to `cas_update()`.

- [ ] **Step 6: Write failing public return tests**

```python
def test_public_return_directly_executes_with_inspection(app) -> None:
    context = seed_public_in_use_context()
    grant_permissions(context.manager, "asset:usage:manage")
    register_usage_return_handlers()
    db.session.commit()
    result = asset_return_service.submit_public(
        {
            "asset_ids": [context.main_asset.id],
            "return_location_id": context.return_location.id,
            "idempotency_key": "public-return-1",
            "items": [
                {"asset_id": context.main_asset.id, "condition": "NORMAL"},
                {"asset_id": context.child_asset.id, "condition": "NORMAL"},
            ],
        },
        context.manager.id,
    )
    assert result["execution_status"] == ExecutionStatus.SUCCESS.value
    assert all(asset.status == AssetStatus.IDLE.value for asset in result_assets())
```

The invalid-type test changes one child to personal use and asserts no request. A single public-return request may contain assets from different public objects, because all are cleared to the same return location. Replay submits twice and asserts one operation, one attempt, two lifecycle rows, and one log.

Add fixture helpers in this task: `seed_public_in_use_context()` sets both assets to `IN_USE/PUBLIC` with the seeded public object; `seed_approved_personal_return()` sets both assets to the employee's `IN_USE/PERSONAL`, submits a return, dispatches one approved provider event, and returns `(context, operation)`; `result_assets()` queries the two seeded asset IDs after `db.session.expire_all()`.

- [ ] **Step 7: Implement public return submission**

Implement `submit_public(payload, actor_id)` in this exact order: permission, idempotency replay, expansion, scope, public-state validation, exact item-set validation, location validation, common request, return request/items, direct confirmation, serialization.

Require manager permission, scope, `IN_USE/PUBLIC`, selectable return location, and exact inspection items after expansion. Create `PUBLIC_RETURN` with `DIRECT/AUTO_ON_APPROVAL`, save confirmed rows, and call `confirm_direct()`.

- [ ] **Step 8: Verify and commit**

```bash
.venv/bin/python -m pytest tests/test_asset_return_service.py \
  tests/test_operation_executor.py tests/test_asset_business_locks.py -q
git add app/services/asset_return_service.py \
  app/operations/asset_usage_return_handlers.py \
  tests/test_asset_return_service.py
git commit -m "feat: implement asset return flows"
```

Expected: all pass.

## Task 5: Feature list/detail queries

**Files:**

- Modify: `back/app/repositories/asset_usage_return_repository.py`
- Modify: `back/app/services/asset_usage_service.py`
- Modify: `back/app/services/asset_return_service.py`
- Modify: `back/tests/test_asset_usage_service.py`
- Modify: `back/tests/test_asset_return_service.py`
- Modify: `back/tests/asset_usage_return_fixtures.py`

- [ ] **Step 1: Write failing query tests**

```python
def test_target_employee_can_view_personal_usage_detail(app) -> None:
    context, operation = seed_pending_personal_usage()
    result = asset_usage_service.get(operation.id, context.employee.id)
    assert result["id"] == operation.id
    assert result["target_user_id"] == context.employee.id


def test_manager_cannot_view_request_with_any_out_of_scope_asset(app) -> None:
    context, operation = seed_cross_scope_usage()
    grant_scoped_manager_permission(context.manager, context.organization.id)
    db.session.commit()
    with pytest.raises(BusinessException, match="无权查看"):
        asset_usage_service.get(operation.id, context.manager.id)
```

Add a newest-first page test with two operations and `size=1`; an applicant return page test with two employees; and a detail-shape test asserting snapshots, feature fields, inspection values, and `allowed_actions`.

Add `grant_scoped_manager_permission()` using a role with `DataScope.CUSTOM` plus `RoleDataScopeOrganization`, and `seed_cross_scope_usage()` with the main and child in different organizations. Both helpers return persisted rows and commit nothing implicitly.

- [ ] **Step 2: Run query tests and verify RED**

```bash
.venv/bin/python -m pytest tests/test_asset_usage_service.py \
  tests/test_asset_return_service.py -k "page or detail" -q
```

Expected: query methods are missing.

- [ ] **Step 3: Add repository page/access queries**

Add repository methods `page_usage(*, actor_id, can_manage, organization_ids, page, size) -> Page[tuple[OperationRequest, AssetUsageRequest]]` and `page_returns(...) -> Page[tuple[OperationRequest, AssetReturnRequest]]`.

Applicant sees own requests; personal usage target sees that usage request; manager visibility requires permission and no request asset outside its organization set. `None` means all organizations. Count distinct operation IDs with exactly the same filters as the page query.

- [ ] **Step 4: Implement Service page/detail methods**

Expose `page(*, actor_id, page_index, size) -> PageResult` and `get(operation_request_id, actor_id) -> dict[str, Any]` in both feature Services. The implementation must call only the feature repository for visibility, then the shared serializer after the visible row is established.

Return common snapshots, feature fields, and allowed actions. Waiting personal returns expose `CONFIRM_RETURN` only to a manager with permission and full scope. Failed execution continues using common retry/terminate endpoints.

- [ ] **Step 5: Verify and commit**

```bash
.venv/bin/python -m pytest tests/test_asset_usage_service.py \
  tests/test_asset_return_service.py -q
git add app/repositories/asset_usage_return_repository.py \
  app/services/asset_usage_service.py app/services/asset_return_service.py \
  tests/test_asset_usage_service.py tests/test_asset_return_service.py
git commit -m "feat: query usage return requests"
```

Expected: all service tests pass.

## Task 6: Local Feishu event service

**Files:**

- Create: `back/app/services/local_feishu_service.py`
- Create: `back/tests/test_asset_usage_return_api.py`

- [ ] **Step 1: Write failing local-provider tests**

```python
def test_usage_target_employee_can_mock_approve_once(app) -> None:
    context, operation = seed_pending_personal_usage()
    register_usage_return_handlers()
    payload = {"action": "APPROVE", "external_event_id": "usage-approved-1"}
    result = local_feishu_service.act(operation.id, payload, context.employee.id)
    replay = local_feishu_service.act(operation.id, payload, context.employee.id)
    assert result["execution_status"] == ExecutionStatus.SUCCESS.value
    assert replay["id"] == result["id"]
    assert db.session.query(ExternalApprovalEvent).count() == 1


def test_mock_reject_persists_reason_in_external_event_payload(app) -> None:
    context, operation = seed_pending_personal_usage()
    local_feishu_service.act(
        operation.id,
        {
            "action": "REJECT",
            "external_event_id": "usage-rejected-1",
            "reason": "device not received",
        },
        context.employee.id,
    )
    assert db.session.query(ExternalApprovalEvent).one().payload["reason"] == (
        "device not received"
    )
```

Add non-target, manager-return-approval, applicant-withdrawal, and duplicate-event tests with the same concrete `act()` pattern and explicit permission/result assertions.

- [ ] **Step 2: Run tests and verify RED**

```bash
.venv/bin/python -m pytest tests/test_asset_usage_return_api.py -k mock -q
```

Expected: `local_feishu_service` is missing.

- [ ] **Step 3: Implement participant checks and dispatch**

Expose `act(operation_request_id, payload, actor_id) -> dict[str, Any]` as the module's only public function.

Rules:

1. Require Flask `TESTING`, `DEBUG`, or `LOCAL_FEISHU_ENABLED=True`; otherwise raise `NOT_FOUND`. This enables the existing DevConfig without changing config files and remains disabled in ProdConfig.
2. Usage `APPROVE/REJECT`: actor equals target employee.
3. Return `APPROVE/REJECT`: actor has `asset:usage:manage` and full request scope.
4. `WITHDRAW`: actor equals applicant.
5. Dispatch only through `approval_provider_service.handle_callback()`.
6. Enrich the matching `ExternalApprovalEvent.payload` with normalized reason and commit.
7. Return the appropriate feature Service detail serialization.
8. Never assign approval or execution status directly.

- [ ] **Step 4: Verify and commit**

```bash
.venv/bin/python -m pytest tests/test_asset_usage_return_api.py -k mock \
  tests/test_approval_providers.py -q
git add app/services/local_feishu_service.py tests/test_asset_usage_return_api.py
git commit -m "feat: simulate feishu usage return events"
```

Expected: all local and common provider tests pass.

## Task 7: HTTP blueprints

**Files:**

- Create: `back/app/api/asset_usage.py`
- Create: `back/app/api/asset_returns.py`
- Create: `back/app/api/local_feishu.py`
- Modify: `back/tests/test_asset_usage_return_api.py`
- Modify: `back/tests/asset_usage_return_fixtures.py`

- [ ] **Step 1: Add explicit test-only app registration**

Do not modify production aggregation on this branch:

```python
@pytest.fixture()
def feature_app():
    app = create_app(config=TestConfig)
    app.register_blueprint(asset_usage.bp)
    app.register_blueprint(asset_returns.bp)
    app.register_blueprint(local_feishu.bp)
    register_usage_return_handlers()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
```

Register blueprints before creating or using the client.

Add `seed_http_context(client)` to the fixture module. It seeds context, grants manager and employee permissions, commits, logs both users in through `/api/v1/auth/login`, and returns `(context, HttpHeaders(manager={...}, employee={...}))` where each mapping contains its bearer token.

- [ ] **Step 2: Write failing API tests**

```python
def test_personal_usage_post_returns_common_envelope(feature_client) -> None:
    context, headers = seed_http_context(feature_client)
    response = feature_client.post(
        "/api/v1/asset-usage-requests/personal",
        headers=headers.manager,
        json={
            "asset_ids": [context.main_asset.id],
            "target_user_id": context.employee.id,
        },
    )
    body = response.get_json()
    assert response.status_code == 200
    assert body["code"] == 200
    assert body["data"]["operation_type"] == OperationType.PERSONAL_USE.value


def test_blueprints_expose_only_get_and_post(feature_app) -> None:
    methods = {
        method
        for rule in feature_app.url_map.iter_rules()
        if "asset-usage" in rule.rule or "asset-return" in rule.rule
        for method in rule.methods
        if method not in {"HEAD", "OPTIONS"}
    }
    assert methods <= {"GET", "POST"}
```

Add concrete client calls for public usage, usage page/detail, self return, admin confirmation, public return, disabled mock profile, malformed schema envelope, and a source-text assertion that API files contain neither `app.models` nor `app.extensions`.

- [ ] **Step 3: Run API tests and verify RED**

```bash
.venv/bin/python -m pytest tests/test_asset_usage_return_api.py -q
```

Expected: API leaf modules are missing.

- [ ] **Step 4: Implement blueprints**

Use prefixes:

```python
bp = Blueprint("asset_usage", __name__, url_prefix="/api/v1/asset-usage-requests")
bp = Blueprint("asset_returns", __name__, url_prefix="/api/v1/asset-return-requests")
bp = Blueprint("local_feishu_usage_return", __name__, url_prefix="/api/v1")
```

Every route has `@jwt_required()`, uses a module-level Schema, calls only a Service, and returns `Result.success(data).to_dict()`. Implement exactly the GET/POST routes from the design. Keep mock routes in the separate blueprint so production integration can omit it entirely.

- [ ] **Step 5: Verify API and repository conventions**

```bash
.venv/bin/python -m pytest tests/test_asset_usage_return_api.py \
  tests/test_auth.py tests/test_operation_api.py -q
cd ..
./scripts/guard-conventions.sh
```

Expected: tests pass; no Blueprint imports model/db; no PUT/PATCH/DELETE route.

- [ ] **Step 6: Commit**

```bash
git add back/app/api/asset_usage.py back/app/api/asset_returns.py \
  back/app/api/local_feishu.py back/tests/test_asset_usage_return_api.py
git commit -m "feat: expose usage return api"
```

## Task 8: Concurrency, rollback, and idempotency proof

**Files:**

- Create: `back/tests/test_asset_usage_return_concurrency.py`
- Modify only after a failing test proves a defect:
  - `back/app/services/asset_usage_service.py`
  - `back/app/services/asset_return_service.py`
  - `back/app/operations/asset_usage_return_handlers.py`
  - `back/app/repositories/asset_usage_return_repository.py`

- [ ] **Step 1: Write concurrency and rollback tests**

Use the existing `ThreadPoolExecutor` + `Barrier` pattern from `test_approval_providers.py`. Each worker opens its own app context and returns the persisted operation ID. Add six tests with these exact assertions:

```python
assert operation_ids[0] == operation_ids[1]
assert db.session.query(OperationRequest).count() == 1
assert db.session.query(AssetBusinessLock).count() == 2
assert db.session.query(OperationExecutionAttempt).count() == 1
assert db.session.query(AssetLifecycleRecord).count() in {0, 2}
```

The duplicate event and duplicate confirmation cases require two lifecycle rows; the forced second-CAS failure requires zero. The version-change test requires `FAILED`, one safe attempt, and retained locks. Rejected/withdrawn tests require zero locks and unchanged assets.

The CAS rollback test asserts both assets keep original state/version, no lifecycle or success operation log exists, one safe failed attempt exists, and business locks remain.

- [ ] **Step 2: Run tests and verify meaningful RED**

```bash
.venv/bin/python -m pytest tests/test_asset_usage_return_concurrency.py -q
```

Expected before hardening: a failure identifies missing concurrent replay, action claim, or rollback behavior. A test that already passes requires no production change.

- [ ] **Step 3: Apply only root-cause fixes**

Use `superpowers:systematic-debugging` per failure. Keep changes inside the four listed feature modules. If a validated fix requires the common kernel, stop and record an integration blocker instead of copying common logic.

- [ ] **Step 4: Run the concurrency module three times**

```bash
for run in 1 2 3; do
  .venv/bin/python -m pytest tests/test_asset_usage_return_concurrency.py -q || exit 1
done
```

Expected: three consecutive passes.

- [ ] **Step 5: Commit**

```bash
git add back/tests/test_asset_usage_return_concurrency.py \
  back/app/services/asset_usage_service.py \
  back/app/services/asset_return_service.py \
  back/app/operations/asset_usage_return_handlers.py \
  back/app/repositories/asset_usage_return_repository.py
git commit -m "test: harden usage return transactions"
```

## Task 9: Full verification and integration handoff

- [ ] **Step 1: Verify changed-file boundary**

```bash
git diff --name-only fc6fb60...HEAD
```

Expected: only the spec/plan and leaf files listed here. No public aggregation, operation kernel, config, Docker, Redis, seed, or migration file.

- [ ] **Step 2: Run backend gates**

```bash
cd back
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app/ config.py
.venv/bin/python -m pytest
```

Expected: zero lint/type failures and all tests pass.

- [ ] **Step 3: Run guards and diff checks**

```bash
cd ..
./scripts/guard-conventions.sh
git diff --check fc6fb60...HEAD
git status --short
```

Expected: guard and diff check exit 0; only intentional plan checkbox tracking may remain before its commit.

- [ ] **Step 4: Exercise the Flask boundary**

```bash
cd back
.venv/bin/python -m pytest tests/test_asset_usage_return_api.py -vv
```

Expected: all four flows pass through Flask test client, JWT, Schema, Service, executor, CAS, and database.

- [ ] **Step 5: Commit plan tracking changes**

```bash
git add docs/superpowers/plans/2026-07-21-asset-usage-return.md
git commit -m "docs: complete usage return implementation plan"
```

- [ ] **Step 6: Report the post-merge integration checklist**

Do not implement these on the feature branch:

```text
1. Import the three models in app/models/__init__.py.
2. Import repository/service leaves only if project aggregation requires them.
3. Register usage and return blueprints; register local Feishu only in dev/test.
4. Register all four operation handlers in app factory wiring.
5. Seed asset:usage:manage and asset:return:self.
6. Include the three new tables in 005_parallel_operation_features.py.
7. Run SQLite upgrade/downgrade, MySQL migration review, full tests, and live smoke tests.
```

## Task 10: Independent six-dimension review loop

- [ ] **Step 1: Start one independent read-only review agent**

Give it the design, this plan, `fc6fb60...HEAD`, and these dimensions:

```text
需求完整性、逻辑正确性、边界情况、代码质量、测试覆盖、实际运行结果
```

It must not modify files. It returns a prioritized checklist with file/line evidence and reproduction commands, or `PASS`.

- [ ] **Step 2: Main thread validates and fixes findings**

Reproduce every item. Use `superpowers:receiving-code-review`, apply only validated TDD fixes, rerun targeted and full gates, and commit focused changes.

- [ ] **Step 3: Ask the same agent to re-verify the new HEAD**

It rechecks all six dimensions and earlier findings. Repeat main-thread fix and same-agent re-review until `PASS` or a concrete branch-boundary blocker is proven.

- [ ] **Step 4: Produce completion evidence**

Report branch, commit list, changed files, full gate commands, test count, six-dimension result, and post-merge integration items. Do not claim completion without fresh evidence.
