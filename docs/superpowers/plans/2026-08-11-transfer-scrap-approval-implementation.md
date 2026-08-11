# Transfer and Scrap Approval Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route asset transfer and scrap submissions through the existing immutable operation and approval kernel so assets change only after final approval.

**Architecture:** Keep the current HTTP paths, but replace direct lifecycle commands with feature-specific submission services that persist request details, operation asset snapshots, approval tasks, and business locks. Register dedicated transfer and scrap handlers with `operation_executor`; handlers revalidate the immutable request and apply the whole batch transactionally after final approval.

**Tech Stack:** Flask 3, SQLAlchemy 2, Alembic, Marshmallow, pytest, React 18, TypeScript, React Query, Ant Design, Node test runner.

**Design spec:** `docs/superpowers/specs/2026-08-11-transfer-scrap-approval-design.md`

---

## File Map

### Backend files to create

- `back/app/models/asset_lifecycle_request.py`: transfer request, scrap request, and per-asset scrap detail models.
- `back/app/repositories/asset_lifecycle_request_repository.py`: focused persistence queries for the new request details.
- `back/migrations/versions/019_asset_lifecycle_approval.py`: tables, foreign keys, unique constraints, checks, and indexes.
- `back/app/services/asset_lifecycle_submission.py`: shared target normalization, scoped asset loading, child expansion, and snapshot helpers.
- `back/app/services/asset_transfer_service.py`: transfer submission transaction.
- `back/app/services/asset_scrap_service.py`: scrap submission transaction.
- `back/app/operations/asset_lifecycle_execution.py`: shared approved-request loading, lock verification, and immutable snapshot checks.
- `back/app/operations/asset_transfer_handler.py`: approved transfer revalidation and execution.
- `back/app/operations/asset_scrap_handler.py`: approved scrap revalidation and execution.
- `back/tests/test_asset_lifecycle_request_models.py`: model and repository contracts.
- `back/tests/test_asset_lifecycle_approval_migration.py`: migration chain and DDL contracts.
- `back/tests/asset_lifecycle_approval_fixtures.py`: test-only users, assets, flows, and request helpers.
- `back/tests/test_asset_lifecycle_submission.py`: schema, transfer submission, and scrap submission tests.
- `back/tests/test_asset_lifecycle_execution.py`: handler and transactional execution tests.
- `back/tests/test_asset_lifecycle_approval_api.py`: JWT/API and end-to-end approval tests.

### Frontend files to create

- `front/src/features/operations/lifecycleResult.ts`: discriminated immediate-command versus approval-request result model.
- `front/src/features/operations/lifecycleResult.test.ts`: success copy and invalidation contract tests.

### Existing files to modify

- `back/app/enums/__init__.py`: add `SCRAP` to `OperationType`.
- `back/app/models/__init__.py`: register/export the new models.
- `back/app/repositories/__init__.py`: export the new repositories.
- `back/app/services/__init__.py`: expose the two submission services.
- `back/app/services/operation_service.py`: expose a service-safe serializer for newly created or replayed requests.
- `back/app/services/approval_engine.py`: filter snapshotted approvers against every organization in a batch.
- `back/app/schemas/asset_management.py`: add normalized idempotency keys and duplicate-item validation.
- `back/app/api/asset_management.py`: call submission services for transfer and scrap.
- `back/app/__init__.py`: register the two new operation handlers.
- `back/app/services/asset_management_service.py`: remove direct public transfer/scrap entry points after handlers cover their behavior.
- `back/tests/test_approval_engine.py`: multi-organization approver coverage tests.
- `back/tests/test_asset_management_service.py`: retain direct maintenance/repair coverage and remove superseded direct transfer/scrap tests.
- `front/src/api/assetManagement.ts`: return `OperationRequest` for transfer/scrap and send idempotency keys.
- `front/src/features/operations/Workflows.tsx`: show pending-approval success state and refresh workflow queries.
- `docs/testing/pilot/defect-register.md`: move `PILOT-009` to `READY_FOR_RETEST` only after gates pass.
- `docs/testing/pilot/coverage-baseline.md`: record focused and full regression evidence.
- `docs/testing/pilot/2026-08-11-environment-automation-gate.md`: add the approval-gate evidence and preserve unrelated blockers.

### Execution safety

The current workspace contains substantial pre-existing uncommitted work. The commit commands below assume execution in a clean isolated worktree containing the agreed baseline. If execution stays in the current workspace, inspect every staged diff and stage only the implementation hunks; never absorb unrelated user changes into these commits. Do not discard the current workspace changes when preparing an isolated worktree.

## Task 1: Add Lifecycle Request Models and Repositories

**Files:**
- Create: `back/app/models/asset_lifecycle_request.py`
- Create: `back/app/repositories/asset_lifecycle_request_repository.py`
- Create: `back/tests/test_asset_lifecycle_request_models.py`
- Modify: `back/app/enums/__init__.py`
- Modify: `back/app/models/__init__.py`
- Modify: `back/app/repositories/__init__.py`

- [ ] **Step 1: Write failing model metadata and repository tests**

Create tests that import the new classes, verify `OperationType.SCRAP`, verify required columns, and verify one-to-one uniqueness:

```python
from sqlalchemy import UniqueConstraint

from app.enums import OperationType
from app.models import (
    AssetScrapRequest,
    AssetScrapRequestItem,
    AssetTransferRequest,
)
from app.repositories import (
    asset_scrap_request_item_repository,
    asset_scrap_request_repository,
    asset_transfer_request_repository,
)


def _unique_columns(model: type) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def test_lifecycle_request_model_contracts() -> None:
    assert OperationType.SCRAP.value == "SCRAP"
    assert ("operation_request_id",) in _unique_columns(AssetTransferRequest)
    assert ("operation_request_id",) in _unique_columns(AssetScrapRequest)
    assert ("operation_request_asset_id",) in _unique_columns(
        AssetScrapRequestItem
    )
    assert AssetScrapRequest.__table__.c.scrap_date.nullable is False
    assert AssetScrapRequestItem.__table__.c.disposition.nullable is False
    assert AssetScrapRequestItem.__table__.c.scrap_amount.nullable is True


def test_lifecycle_request_repositories_are_registered() -> None:
    assert asset_transfer_request_repository.model is AssetTransferRequest
    assert asset_scrap_request_repository.model is AssetScrapRequest
    assert asset_scrap_request_item_repository.model is AssetScrapRequestItem
```

- [ ] **Step 2: Run the tests and verify the missing imports fail**

Working directory: `back`

Run: `.venv/bin/python -m pytest tests/test_asset_lifecycle_request_models.py -q`

Expected: collection fails because the models and repositories do not exist.

- [ ] **Step 3: Implement the operation type and persistence models**

Add `SCRAP = "SCRAP"` to `OperationType`. Create three SQLAlchemy models with these exact ownership rules:

```python
class AssetTransferRequest(TimestampMixin, db.Model):
    __tablename__ = "asset_transfer_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_id: Mapped[int] = mapped_column(
        ForeignKey("operation_requests.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True
    )
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("asset_locations.id", ondelete="RESTRICT"), nullable=True
    )
    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    holder_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    public_object_id: Mapped[int | None] = mapped_column(
        ForeignKey("public_usage_objects.id", ondelete="RESTRICT"), nullable=True
    )
    target_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class AssetScrapRequest(TimestampMixin, db.Model):
    __tablename__ = "asset_scrap_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_id: Mapped[int] = mapped_column(
        ForeignKey("operation_requests.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    scrap_date: Mapped[date] = mapped_column(Date, nullable=False)


class AssetScrapRequestItem(TimestampMixin, db.Model):
    __tablename__ = "asset_scrap_request_items"
    __table_args__ = (
        CheckConstraint(
            "disposition IN ('SCRAP', 'DETACH')",
            name="ck_asset_scrap_item_disposition",
        ),
        CheckConstraint(
            "(disposition = 'SCRAP' AND scrap_amount IS NOT NULL "
            "AND scrap_amount >= 0) OR "
            "(disposition = 'DETACH' AND scrap_amount IS NULL)",
            name="ck_asset_scrap_item_amount",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_asset_id: Mapped[int] = mapped_column(
        ForeignKey("operation_request_assets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    disposition: Mapped[str] = mapped_column(String(16), nullable=False)
    scrap_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
```

Use standard imports, `TimestampMixin`, and the repository `BaseRepository` pattern already used by `asset_usage_return_repository.py`.

- [ ] **Step 4: Implement focused repository lookups and exports**

Each request repository must implement `find_by_operation(operation_request_id)`. The item repository must implement an ordered lookup joined through `OperationRequestAsset`:

```python
def find_by_operation(
    self, operation_request_id: int
) -> list[AssetScrapRequestItem]:
    statement = (
        select(AssetScrapRequestItem)
        .join(
            OperationRequestAsset,
            OperationRequestAsset.id
            == AssetScrapRequestItem.operation_request_asset_id,
        )
        .where(OperationRequestAsset.operation_request_id == operation_request_id)
        .order_by(OperationRequestAsset.asset_id.asc())
    )
    return list(db.session.scalars(statement).all())
```

Register models in `app.models` and repository classes/instances in `app.repositories`.

- [ ] **Step 5: Run focused model tests**

Working directory: `back`

Run: `.venv/bin/python -m pytest tests/test_asset_lifecycle_request_models.py -q`

Expected: all tests pass.

- [ ] **Step 6: Run backend static checks for the new modules**

Working directory: `back`

Run: `.venv/bin/ruff check app/models/asset_lifecycle_request.py app/repositories/asset_lifecycle_request_repository.py tests/test_asset_lifecycle_request_models.py`

Expected: no findings.

- [ ] **Step 7: Commit Task 1**

```bash
git add back/app/enums/__init__.py back/app/models/__init__.py back/app/models/asset_lifecycle_request.py back/app/repositories/__init__.py back/app/repositories/asset_lifecycle_request_repository.py back/tests/test_asset_lifecycle_request_models.py
git commit -m "feat(asset): add lifecycle approval request models"
```

## Task 2: Add the Alembic Migration

**Files:**
- Create: `back/migrations/versions/019_asset_lifecycle_approval.py`
- Create: `back/tests/test_asset_lifecycle_approval_migration.py`

- [ ] **Step 1: Write failing migration-chain and DDL tests**

The test must load revision `019`, assert `down_revision == "018"`, compile against MySQL, and check all three tables and constraints:

```python
MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "019_asset_lifecycle_approval.py"
)


def _load_migration(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_asset_lifecycle_approval_revision_follows_user_preferences() -> None:
    module = _load_migration(MIGRATION, "migration_019")
    assert module.revision == "019"
    assert module.down_revision == "018"


def test_asset_lifecycle_approval_ddl_compiles_for_mysql() -> None:
    module = _load_migration(MIGRATION, "migration_019_mysql")
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="mysql",
        opts={"as_sql": True, "literal_binds": True, "output_buffer": output},
    )
    with Operations.context(context):
        module.upgrade()
    sql = output.getvalue()
    assert "CREATE TABLE asset_transfer_requests" in sql
    assert "CREATE TABLE asset_scrap_requests" in sql
    assert "CREATE TABLE asset_scrap_request_items" in sql
    assert "ck_asset_scrap_item_disposition" in sql
    assert "ck_asset_scrap_item_amount" in sql
    assert "ON DELETE CASCADE" in sql
```

Also add an online SQLite upgrade/downgrade test that starts from revision `018`, upgrades to `019`, checks the tables, downgrades to `018`, and verifies their removal.

- [ ] **Step 2: Run the migration tests and verify revision 019 is missing**

Working directory: `back`

Run: `.venv/bin/python -m pytest tests/test_asset_lifecycle_approval_migration.py -q`

Expected: tests fail because the migration file does not exist.

- [ ] **Step 3: Implement revision 019**

Create all columns represented by the Task 1 models. Use explicit foreign-key names, index names, unique-constraint names, and the two scrap-item checks. The revision header must be:

```python
revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None
```

`upgrade()` creates request headers before item rows. `downgrade()` drops `asset_scrap_request_items`, then `asset_scrap_requests`, then `asset_transfer_requests`. Do not seed roles, users, flow definitions, versions, or assignee rules.

- [ ] **Step 4: Run migration tests and the existing migration suite**

Working directory: `back`

Run: `.venv/bin/python -m pytest tests/test_asset_lifecycle_approval_migration.py tests/test_migrations.py -q`

Expected: all tests pass.

- [ ] **Step 5: Run a real local upgrade check**

Working directory: `back`

Run: `FLASK_APP=manage.py .venv/bin/flask db upgrade`

Expected: Alembic reports upgrade from `018` to `019` or reports that the database is already at head.

- [ ] **Step 6: Commit Task 2**

```bash
git add back/migrations/versions/019_asset_lifecycle_approval.py back/tests/test_asset_lifecycle_approval_migration.py
git commit -m "feat(asset): migrate lifecycle approval requests"
```

## Task 3: Harden Schemas and Multi-Organization Approval Resolution

**Files:**
- Modify: `back/app/schemas/asset_management.py`
- Modify: `back/app/services/approval_engine.py`
- Modify: `back/tests/test_approval_engine.py`
- Create: `back/tests/test_asset_lifecycle_submission.py`

- [ ] **Step 1: Write failing schema tests**

Add tests for whitespace normalization, blank keys, and duplicate assets on both schemas:

```python
def _valid_transfer_payload() -> dict:
    return {
        "items": [{"asset_id": 7, "version": 1}],
        "location_id": 3,
        "reason": "办公地点调整",
    }


def _valid_scrap_payload() -> dict:
    return {
        "items": [{"asset_id": 7, "version": 1}],
        "scrap_date": "2026-08-11",
        "scrap_amount": "100.00",
        "child_action": "BLOCK",
        "reason": "设备达到报废条件",
    }


@pytest.mark.parametrize("schema", [TransferAssetsSchema(), ScrapAssetsSchema()])
def test_lifecycle_schema_normalizes_idempotency_key(schema: Schema) -> None:
    payload = _valid_transfer_payload() if isinstance(
        schema, TransferAssetsSchema
    ) else _valid_scrap_payload()
    payload["idempotency_key"] = "  request-key  "
    assert schema.load(payload)["idempotency_key"] == "request-key"


@pytest.mark.parametrize("schema", [TransferAssetsSchema(), ScrapAssetsSchema()])
def test_lifecycle_schema_rejects_duplicate_assets(schema: Schema) -> None:
    payload = _valid_transfer_payload() if isinstance(
        schema, TransferAssetsSchema
    ) else _valid_scrap_payload()
    payload["items"] = [
        {"asset_id": 7, "version": 1},
        {"asset_id": 7, "version": 1},
    ]
    with pytest.raises(ValidationError, match="资产不能重复选择"):
        schema.load(payload)
```

- [ ] **Step 2: Write a failing all-organizations approver test**

Extend `test_approval_engine.py` with a two-organization request. Configure one approver with `ALL` scope and one approver with only the anchor organization. Initialize with both organization IDs and assert only the all-scope approver is snapshotted:

```python
_engine().initialize(
    operation,
    version.id,
    first_organization.id,
    required_organization_ids={first_organization.id, second_organization.id},
)

tasks = db.session.query(ApprovalTask).all()
assert [task.approver_id for task in tasks] == [all_scope_approver.id]
```

- [ ] **Step 3: Run focused tests and verify they fail**

Working directory: `back`

Run: `.venv/bin/python -m pytest tests/test_asset_lifecycle_submission.py tests/test_approval_engine.py -q`

Expected: schema assertions fail and `approval_engine.initialize()` rejects the new keyword argument.

- [ ] **Step 4: Add the shared lifecycle schema contract**

Add `idempotency_key` and a schema-level uniqueness check shared by transfer and scrap:

```python
class _LifecycleRequestSchema(Schema):
    items = fields.List(
        fields.Nested(LifecycleAssetTargetSchema),
        required=True,
        validate=validate.Length(min=1, max=100),
    )
    idempotency_key = fields.String(
        required=False,
        allow_none=True,
        validate=validate.Length(min=1, max=191),
    )

    @pre_load
    def normalize_idempotency_key(self, data: Any, **_kwargs: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        normalized = dict(data)
        key = normalized.get("idempotency_key")
        if isinstance(key, str):
            normalized["idempotency_key"] = key.strip()
        return normalized

    @validates_schema
    def require_unique_assets(self, data: dict, **_kwargs: Any) -> None:
        asset_ids = [item["asset_id"] for item in data["items"]]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValidationError("资产不能重复选择", field_name="items")
```

Make `TransferAssetsSchema` and `ScrapAssetsSchema` inherit this base and remove their duplicate `items` declarations.

- [ ] **Step 5: Filter approval candidates by the complete organization set**

Keep current callers compatible by adding an optional keyword-only set:

```python
def initialize(
    operation: OperationRequest,
    flow_version_id: int,
    organization_id: int,
    *,
    required_organization_ids: set[int] | None = None,
) -> None:
    required_ids = required_organization_ids
```

After role/user rules resolve candidates, retain a user only when:

```python
def _covers_organizations(user_id: int, organization_ids: set[int]) -> bool:
    accessible = permission_service.accessible_organization_ids(user_id)
    return accessible is None or organization_ids.issubset(accessible)
```

Apply the filter before self-approval removal and before the empty-layer check only when `required_ids` is not `None`. Existing stock-in and existing approval-engine callers omit the new argument and preserve their current explicit-user behavior. Transfer and scrap always pass their complete organization set, including a one-organization set.

- [ ] **Step 6: Run focused and approval-engine tests**

Working directory: `back`

Run: `.venv/bin/python -m pytest tests/test_asset_lifecycle_submission.py tests/test_approval_engine.py -q`

Expected: all tests pass.

- [ ] **Step 7: Commit Task 3**

```bash
git add back/app/schemas/asset_management.py back/app/services/approval_engine.py back/tests/test_approval_engine.py back/tests/test_asset_lifecycle_submission.py
git commit -m "feat(approval): validate lifecycle request scope"
```

## Task 4: Implement Transfer Submission

**Files:**
- Create: `back/app/services/asset_lifecycle_submission.py`
- Create: `back/app/services/asset_transfer_service.py`
- Create: `back/tests/asset_lifecycle_approval_fixtures.py`
- Modify: `back/app/services/__init__.py`
- Modify: `back/app/services/operation_service.py`
- Modify: `back/tests/test_asset_lifecycle_submission.py`

- [ ] **Step 1: Add focused transfer submission fixtures**

Create a test factory that returns named users, two organizations, selectable locations, one complete main asset, one direct child, and a published flow. Use this explicit interface:

```python
@dataclass(frozen=True)
class LifecycleApprovalContext:
    applicant: User
    first_approver: User
    second_approver: User
    organization: Organization
    other_organization: Organization
    location: AssetLocation
    other_location: AssetLocation
    main_asset: Asset
    child_asset: Asset
```

Implement `seed_lifecycle_context() -> LifecycleApprovalContext` with direct model constructors, following `_seed_context()` in `test_asset_management_service.py`. Implement `publish_user_flow(operation_type: str, layers: list[tuple[User, bool]]) -> ApprovalFlowVersion` with the `ApprovalFlowDefinition`, `ApprovalFlowVersion`, `ApprovalFlowLayer`, and `ApprovalFlowAssigneeRule` constructors used by `_flow()` in `test_approval_engine.py`.

The applicant role must include `asset:view`, `asset:amount:view`, `asset:transfer`, `asset:scrap`, and `operation:request:view`. Approver roles must include `approval:task:view` and `approval:task:approve`. All three users use `DataScope.ALL` unless a test explicitly replaces scope. Also expose this login helper for API tests:

```python
def auth_headers(client, user: User) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": "admin123"},
    )
    token = response.get_json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}
```

- [ ] **Step 2: Write failing transfer submission tests**

Cover no immediate mutation, child expansion, immutable snapshots, lock acquisition, approval initialization, and idempotent replay:

```python
def test_transfer_submit_creates_pending_locked_request_without_mutation(app) -> None:
    context = seed_lifecycle_context()
    publish_user_flow(
        OperationType.TRANSFER.value,
        [(context.first_approver, False)],
    )
    before = (context.main_asset.location_id, context.main_asset.version)

    result = asset_transfer_service.submit(
        {
            "items": [
                {"asset_id": context.main_asset.id, "version": context.main_asset.version}
            ],
            "location_id": context.other_location.id,
            "reason": "办公地点调整",
            "idempotency_key": "transfer-submit-1",
        },
        context.applicant.id,
    )

    db.session.refresh(context.main_asset)
    assert (context.main_asset.location_id, context.main_asset.version) == before
    assert result["operation_type"] == OperationType.TRANSFER.value
    assert result["approval_status"] == ApprovalStatus.PENDING.value
    assert result["execution_status"] == ExecutionStatus.NOT_STARTED.value
    assert {item["asset_id"] for item in result["assets"]} == {
        context.main_asset.id,
        context.child_asset.id,
    }
    assert db.session.query(AssetBusinessLock).count() == 2
    assert db.session.query(ApprovalTask).count() == 1
```

Add a second test that calls `submit()` twice with the same key and asserts one `OperationRequest`, one detail row, and the same request number.

- [ ] **Step 3: Run transfer tests and verify the service is missing**

Working directory: `back`

Run: `.venv/bin/python -m pytest tests/test_asset_lifecycle_submission.py -k transfer -q`

Expected: collection or execution fails because `asset_transfer_service` is unavailable.

- [ ] **Step 4: Implement shared submission asset loading**

`asset_lifecycle_submission.py` must provide:

```python
@dataclass(frozen=True)
class SubmissionAssets:
    assets: list[Asset]
    requested_asset_ids: frozenset[int]
    versions: dict[int, int]
    organization_ids: set[int]


def load_assets_with_direct_children(
    items: list[dict[str, Any]], actor_id: int
) -> SubmissionAssets:
    requested_versions = normalize_targets(items)
    children = asset_repository.find_direct_children(sorted(requested_versions))
    all_versions = dict(requested_versions)
    for child in children:
        all_versions.setdefault(child.id, child.version)
    assets = _load_accessible_unlocked_assets(all_versions, actor_id)
    return SubmissionAssets(
        assets=assets,
        requested_asset_ids=frozenset(requested_versions),
        versions=all_versions,
        organization_ids={asset.organization_id for asset in assets},
    )
```

`_load_accessible_unlocked_assets()` must use `find_many_accessible_for_update()`, reject missing/out-of-scope IDs, reject an existing `AssetBusinessLock`, reject version mismatches, and reject incomplete assets. It must not commit or roll back.

- [ ] **Step 5: Expose a serializer for a service-owned request**

In `operation_service.py`, add:

```python
def serialize_request(
    operation: OperationRequest, actor_id: int
) -> dict[str, Any]:
    return _serialize(operation, actor_id)
```

This function does not perform a second permission lookup because the calling submission service has already authorized and created or replayed the applicant's request.

- [ ] **Step 6: Implement `asset_transfer_service.submit()`**

The implementation order must be:

```python
permission_service.require_permission(actor_id, "asset:transfer")
existing = operation_service.get_by_idempotency_key(
    actor_id,
    OperationType.TRANSFER.value,
    payload.get("idempotency_key") or "",
)
if existing is not None:
    return operation_service.serialize_request(existing, actor_id)

submission = load_assets_with_direct_children(payload["items"], actor_id)
flow = approval_flow_service.get_published(OperationType.TRANSFER.value)
target_data_by_asset_id = _build_transfer_targets(submission.assets, payload)
created = operation_service.create_request(
    operation_type=OperationType.TRANSFER.value,
    applicant_id=actor_id,
    approval_channel=ApprovalChannel.INTERNAL.value,
    approval_execution_mode=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
    assets=submission.assets,
    target_data_by_asset_id=target_data_by_asset_id,
    idempotency_key=payload.get("idempotency_key"),
)
```

If `created.created` is false, return the existing request without inserting detail rows. Otherwise insert `AssetTransferRequest`, initialize approval with `required_organization_ids=submission.organization_ids`, record `TRANSFER_SUBMIT`, commit, and serialize. Wrap the transaction in `try/except`, roll back on every exception, and preserve the operation kernel's idempotency-conflict replay behavior.

- [ ] **Step 7: Run transfer submission and nearby kernel tests**

Working directory: `back`

Run: `.venv/bin/python -m pytest tests/test_asset_lifecycle_submission.py -k transfer tests/test_asset_business_locks.py tests/test_operation_models.py -q`

Expected: all selected tests pass.

- [ ] **Step 8: Commit Task 4**

```bash
git add back/app/services/__init__.py back/app/services/operation_service.py back/app/services/asset_lifecycle_submission.py back/app/services/asset_transfer_service.py back/tests/asset_lifecycle_approval_fixtures.py back/tests/test_asset_lifecycle_submission.py
git commit -m "feat(asset): submit transfer approval requests"
```

## Task 5: Implement Scrap Submission

**Files:**
- Create: `back/app/services/asset_scrap_service.py`
- Modify: `back/app/services/__init__.py`
- Modify: `back/app/services/asset_lifecycle_submission.py`
- Modify: `back/tests/test_asset_lifecycle_submission.py`

- [ ] **Step 1: Write failing scrap submission tests**

Cover two-layer task creation, immutable assets, `BLOCK`, `DETACH`, `SCRAP`, item amounts, self-approval flow rejection, missing-flow rollback, and idempotent replay:

```python
def test_scrap_submit_creates_two_layer_request_without_mutation(app) -> None:
    context = seed_lifecycle_context()
    publish_user_flow(
        OperationType.SCRAP.value,
        [
            (context.first_approver, False),
            (context.second_approver, False),
        ],
    )
    before_status = context.main_asset.status

    result = asset_scrap_service.submit(
        {
            "items": [
                {"asset_id": context.main_asset.id, "version": context.main_asset.version}
            ],
            "scrap_date": date(2026, 8, 11),
            "scrap_amount": Decimal("100.00"),
            "child_action": "SCRAP",
            "reason": "设备达到报废条件",
            "idempotency_key": "scrap-submit-1",
        },
        context.applicant.id,
    )

    db.session.refresh(context.main_asset)
    assert context.main_asset.status == before_status
    assert result["approval_status"] == ApprovalStatus.PENDING.value
    steps = db.session.query(ApprovalStep).order_by(ApprovalStep.level_no).all()
    assert [step.status for step in steps] == ["PENDING", "WAITING"]
    assert db.session.query(AssetScrapRequestItem).count() == 2
```

For `DETACH`, assert the main item is `SCRAP` with the amount and the child item is `DETACH` with `None`. For `BLOCK`, assert no operation, detail, task, or lock rows remain.

- [ ] **Step 2: Run scrap tests and verify the service is missing**

Working directory: `back`

Run: `.venv/bin/python -m pytest tests/test_asset_lifecycle_submission.py -k scrap -q`

Expected: tests fail because `asset_scrap_service` is unavailable.

- [ ] **Step 3: Implement disposition expansion**

Add a helper that returns every locked asset and its immutable disposition:

```python
def scrap_dispositions(
    submission: SubmissionAssets, child_action: str
) -> dict[int, str]:
    auto_children = {
        asset.id
        for asset in submission.assets
        if asset.id not in submission.requested_asset_ids
    }
    if auto_children and child_action == "BLOCK":
        raise BusinessException(
            "主资产仍有关联附属资产，请选择一并报废或先解除关系"
        )
    result = {asset_id: "SCRAP" for asset_id in submission.requested_asset_ids}
    for child_id in auto_children:
        result[child_id] = "DETACH" if child_action == "DETACH" else "SCRAP"
    return result
```

- [ ] **Step 4: Implement `asset_scrap_service.submit()`**

Follow the transfer transaction pattern with these additional rules:

```python
flow = approval_flow_service.get_published(OperationType.SCRAP.value)
if any(layer.allow_self_approval for layer in flow.layers):
    raise BusinessException("报废审批流不允许申请人自审")

dispositions = scrap_dispositions(submission, payload["child_action"])
target_data_by_asset_id = {
    asset.id: {
        "disposition": dispositions[asset.id],
        "scrap_date": payload["scrap_date"].isoformat(),
        "scrap_amount": (
            str(payload["scrap_amount"])
            if dispositions[asset.id] == "SCRAP"
            else None
        ),
    }
    for asset in submission.assets
}
```

After `create_request()`, insert `AssetScrapRequest`. Load operation snapshots, map by `asset_id`, and insert one `AssetScrapRequestItem` per asset. Initialize approval with the complete organization set, record `SCRAP_SUBMIT`, commit, and serialize.

- [ ] **Step 5: Run submission, schema, and lock tests**

Working directory: `back`

Run: `.venv/bin/python -m pytest tests/test_asset_lifecycle_submission.py tests/test_asset_business_locks.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit Task 5**

```bash
git add back/app/services/__init__.py back/app/services/asset_lifecycle_submission.py back/app/services/asset_scrap_service.py back/tests/test_asset_lifecycle_submission.py
git commit -m "feat(asset): submit scrap approval requests"
```

## Task 6: Implement Shared Execution Validation and Transfer Handler

**Files:**
- Create: `back/app/operations/asset_lifecycle_execution.py`
- Create: `back/app/operations/asset_transfer_handler.py`
- Create: `back/tests/test_asset_lifecycle_execution.py`
- Modify: `back/app/__init__.py`

- [ ] **Step 1: Write failing transfer handler tests**

Create a transfer request through the service, mark it approved for direct handler testing, and verify revalidation, execution, audits, and safe handler registration:

Add a local helper before the tests:

```python
def submitted_transfer_request() -> tuple[LifecycleApprovalContext, OperationRequest]:
    context = seed_lifecycle_context()
    publish_user_flow(
        OperationType.TRANSFER.value,
        [(context.first_approver, False)],
    )
    result = asset_transfer_service.submit(
        {
            "items": [
                {"asset_id": context.main_asset.id, "version": context.main_asset.version}
            ],
            "location_id": context.other_location.id,
            "reason": "办公地点调整",
            "idempotency_key": "transfer-execution-1",
        },
        context.applicant.id,
    )
    operation = db.session.get(OperationRequest, result["id"])
    assert operation is not None
    return context, operation
```

```python
def test_transfer_handler_executes_immutable_request(app) -> None:
    context, operation = submitted_transfer_request()
    operation.approval_status = ApprovalStatus.APPROVED.value
    db.session.flush()

    handler = TransferHandler()
    handler.revalidate_for_execution(operation.id)
    handler.execute(operation.id, context.first_approver.id)
    db.session.flush()

    db.session.refresh(context.main_asset)
    db.session.refresh(context.child_asset)
    assert context.main_asset.location_id == context.other_location.id
    assert context.child_asset.location_id == context.other_location.id
    assert context.main_asset.version == 2
    assert context.child_asset.version == 2
    assert db.session.query(AssetLifecycleRecord).filter_by(
        operation_type=OperationType.TRANSFER.value
    ).count() == 2
```

Add tests that tamper with asset version, target snapshot, detail target, and lock owner; each must raise `BusinessException` before any mutation.

- [ ] **Step 2: Run transfer execution tests and verify missing handlers**

Working directory: `back`

Run: `.venv/bin/python -m pytest tests/test_asset_lifecycle_execution.py -k transfer -q`

Expected: collection fails because execution helpers and `TransferHandler` do not exist.

- [ ] **Step 3: Implement shared approved-request loading**

Create this context contract:

```python
@dataclass(frozen=True)
class LifecycleExecutionContext:
    operation: OperationRequest
    snapshots: list[OperationRequestAsset]
    assets: list[Asset]


def load_execution_context(
    operation_request_id: int, expected_operation_type: str
) -> LifecycleExecutionContext:
    operation = operation_request_repository.get(operation_request_id)
    if operation is None or operation.operation_type != expected_operation_type:
        raise BusinessException("资产操作申请不存在或类型不匹配")
    snapshots = operation_request_asset_repository.find_by_request(operation.id)
    asset_ids = [snapshot.asset_id for snapshot in snapshots]
    if not asset_ids or asset_ids != sorted(set(asset_ids)):
        raise BusinessException("资产操作申请快照不完整")
    assets = asset_repository.find_many_for_update(asset_ids)
    if [asset.id for asset in assets] != asset_ids:
        raise BusinessException("资产操作申请与资产不匹配")
    locks = asset_business_lock_repository.find_by_assets(asset_ids)
    if {lock.asset_id for lock in locks} != set(asset_ids) or any(
        lock.operation_request_id != operation.id for lock in locks
    ):
        raise BusinessException("资产操作申请业务锁不完整")
    validate_immutable_asset_snapshots(assets, snapshots)
    return LifecycleExecutionContext(operation, snapshots, assets)
```

`validate_immutable_asset_snapshots()` compares ID, version, status, organization, parent, holder, public object, usage department, location, and manager against canonical `before_data`.

- [ ] **Step 4: Implement `TransferHandler`**

The handler loads `AssetTransferRequest`, reconstructs the exact target changes for every asset, and verifies each `target_data` matches. Allowed source statuses remain `IDLE` and `IN_USE` to preserve the current command contract.

Execution mutates the row-locked ORM assets, increments version once, and records lifecycle entries using the operation request number:

```python
for asset, snapshot in zip(context.assets, context.snapshots, strict=True):
    before = canonical_asset_snapshot(asset)
    for field, value in transfer_changes(detail, asset).items():
        setattr(asset, field, value)
    asset.version += 1
    audit_service.record_asset_lifecycle(
        asset_id=asset.id,
        operation_type=OperationType.TRANSFER.value,
        request_no=context.operation.request_no,
        actor_id=actor_id,
        before_data=before,
        after_data=canonical_asset_snapshot(asset),
        remark=detail.reason,
    )
```

After all assets, record one `audit_service.record_operation()` entry. Do not check `asset:transfer` on the final approver and do not commit.

- [ ] **Step 5: Register the handler and run tests**

Add `TransferHandler` to the `handler_types` tuple in `create_app()`.

Working directory: `back`

Run: `.venv/bin/python -m pytest tests/test_asset_lifecycle_execution.py -k transfer tests/test_operation_executor.py -q`

Expected: all tests pass and registry tests remain green.

- [ ] **Step 6: Commit Task 6**

```bash
git add back/app/__init__.py back/app/operations/asset_lifecycle_execution.py back/app/operations/asset_transfer_handler.py back/tests/test_asset_lifecycle_execution.py
git commit -m "feat(asset): execute approved transfer requests"
```

## Task 7: Implement Scrap Handler and Transactional Relation Changes

**Files:**
- Create: `back/app/operations/asset_scrap_handler.py`
- Modify: `back/app/__init__.py`
- Modify: `back/app/operations/asset_lifecycle_execution.py`
- Modify: `back/tests/test_asset_lifecycle_execution.py`

- [ ] **Step 1: Write failing approved scrap execution tests**

Cover both dispositions and rollback:

Add `submitted_scrap_request(child_action: str)` beside the transfer helper. It must publish two non-self-approving layers, submit the main asset with amount `100.00`, and return the context plus the persisted `OperationRequest`.

```python
def test_scrap_handler_scraps_main_and_detaches_child(app) -> None:
    context, operation = submitted_scrap_request(child_action="DETACH")
    operation.approval_status = ApprovalStatus.APPROVED.value
    db.session.flush()

    handler = ScrapHandler()
    handler.revalidate_for_execution(operation.id)
    handler.execute(operation.id, context.second_approver.id)
    db.session.flush()

    db.session.refresh(context.main_asset)
    db.session.refresh(context.child_asset)
    assert context.main_asset.status == AssetStatus.SCRAPPED.value
    assert context.main_asset.custom_attributes["scrap"]["scrap_amount"] == "100.00"
    assert context.child_asset.status == AssetStatus.IDLE.value
    assert context.child_asset.parent_asset_id is None
```

Add `SCRAP` coverage for both assets. Add a test that corrupts the second item after the first would mutate, invokes through `operation_executor`, and asserts both assets retain their original persisted state while execution becomes `FAILED`.

- [ ] **Step 2: Run scrap execution tests and verify the handler is missing**

Working directory: `back`

Run: `.venv/bin/python -m pytest tests/test_asset_lifecycle_execution.py -k scrap -q`

Expected: tests fail because `ScrapHandler` does not exist.

- [ ] **Step 3: Implement scrap detail and target revalidation**

Load the request header and ordered items. Require one item for every operation asset snapshot and exact agreement between item data and `target_data`. Require source status in `IDLE`, `IN_USE`, or `REPAIRING`.

For `DETACH`, require the asset to remain a direct child of an asset whose request item disposition is `SCRAP`. For `SCRAP`, preserve current child links only when both parent and child have `SCRAP` dispositions in the same request.

- [ ] **Step 4: Implement transactional mutations**

Use these exact state changes:

```python
if item.disposition == "DETACH":
    asset.parent_asset_id = None
    asset.version += 1
    operation_type = "ASSET_RELATION_DETACH"
else:
    custom = dict(asset.custom_attributes)
    custom["scrap"] = {
        "scrap_date": detail.scrap_date.isoformat(),
        "scrap_amount": str(item.scrap_amount),
    }
    asset.status = AssetStatus.SCRAPPED.value
    asset.usage_type = None
    asset.holder_user_id = None
    asset.public_object_id = None
    asset.usage_department_id = None
    asset.custom_attributes = custom
    asset.version += 1
    operation_type = OperationType.SCRAP.value
```

Record per-asset lifecycle rows and one operation log. Do not commit inside the handler.

- [ ] **Step 5: Register the handler and run execution tests**

Add `ScrapHandler` to `handler_types`.

Working directory: `back`

Run: `.venv/bin/python -m pytest tests/test_asset_lifecycle_execution.py tests/test_operation_executor.py -q`

Expected: all tests pass, including full rollback after a handler error.

- [ ] **Step 6: Commit Task 7**

```bash
git add back/app/__init__.py back/app/operations/asset_lifecycle_execution.py back/app/operations/asset_scrap_handler.py back/tests/test_asset_lifecycle_execution.py
git commit -m "feat(asset): execute approved scrap requests"
```

## Task 8: Switch Public APIs and Frontend to Pending Requests

**Files:**
- Create: `back/tests/test_asset_lifecycle_approval_api.py`
- Create: `front/src/features/operations/lifecycleResult.ts`
- Create: `front/src/features/operations/lifecycleResult.test.ts`
- Modify: `back/app/api/asset_management.py`
- Modify: `back/app/services/asset_management_service.py`
- Modify: `back/tests/test_asset_management_service.py`
- Modify: `front/src/api/assetManagement.ts`
- Modify: `front/src/features/operations/Workflows.tsx`

- [ ] **Step 1: Write failing API submission tests**

Authenticate the applicant and assert the route returns an operation request while the asset remains unchanged:

```python
def test_transfer_api_submits_approval_instead_of_mutating_asset(client, app) -> None:
    context = seed_lifecycle_context()
    publish_user_flow(
        OperationType.TRANSFER.value,
        [(context.first_approver, False)],
    )
    response = client.post(
        "/api/v1/asset-actions/transfer",
        headers=auth_headers(client, context.applicant),
        json={
            "items": [
                {"asset_id": context.main_asset.id, "version": context.main_asset.version}
            ],
            "location_id": context.other_location.id,
            "reason": "办公地点调整",
            "idempotency_key": "transfer-api-1",
        },
    )

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["operation_type"] == "TRANSFER"
    assert body["approval_status"] == "PENDING"
    db.session.refresh(context.main_asset)
    assert context.main_asset.location_id == context.location.id
```

Add the corresponding scrap test, JWT-required tests, duplicate-idempotency tests, and missing-flow errors using the unified JSON envelope.

- [ ] **Step 2: Write failing frontend result-model tests**

Define expected copy and cache invalidations before implementation:

```typescript
test('describes a pending approval request', () => {
  const result: LifecycleResult = {
    kind: 'request',
    value: {
      id: 9,
      request_no: 'OPR-9',
      operation_type: 'TRANSFER',
      applicant_id: 1,
      approval_status: 'PENDING',
      execution_status: 'NOT_STARTED',
      assets: [],
    },
  }
  assert.equal(lifecycleSuccessMessage(result), '申请已提交，等待审批，单号 OPR-9')
  assert.deepEqual(lifecycleInvalidationKeys(result), [
    ['operation-requests'],
    ['todo-center'],
  ])
})
```

Also assert immediate repair commands retain “已处理 N 件资产，命令号 X” and asset/dashboard invalidations.

- [ ] **Step 3: Run focused backend and frontend tests and verify failures**

Working directory: `back`

Run: `.venv/bin/python -m pytest tests/test_asset_lifecycle_approval_api.py -q`

Expected: routes still return immediate command results.

Working directory: `front`

Run: `node --experimental-strip-types --test src/features/operations/lifecycleResult.test.ts`

Expected: module is missing.

- [ ] **Step 4: Switch Blueprint calls and remove direct public commands**

Change only the transfer and scrap routes:

```python
return Result.success(
    asset_transfer_service.submit(payload, current_user_id())
).to_dict()
```

```python
return Result.success(
    asset_scrap_service.submit(payload, current_user_id())
).to_dict()
```

After API tests use the new route, remove `transfer()` and `scrap()` from `asset_management_service.__all__` and delete their direct command implementations. Keep repair and unrelated maintenance behavior unchanged. Move or replace superseded direct-command assertions in `test_asset_management_service.py`; do not delete repair, amount validation, public object, relation, audit, or permission coverage.

- [ ] **Step 5: Update frontend API return types**

Import `OperationRequest` and make only transfer/scrap return that type:

Define payload interfaces beside `AssetTarget`:

```typescript
export interface TransferPayload {
  items: AssetTarget[]
  location_id?: number
  manager_id?: number
  holder_user_id?: number | null
  public_object_id?: number | null
  reason: string
  idempotency_key?: string
}

export interface ScrapPayload {
  items: AssetTarget[]
  scrap_date: string
  scrap_amount: string
  child_action: 'BLOCK' | 'DETACH' | 'SCRAP'
  reason: string
  idempotency_key?: string
}
```

```typescript
transfer: (payload: TransferPayload) =>
  http.post<unknown, OperationRequest>('/asset-actions/transfer', {
    ...payload,
    idempotency_key: payload.idempotency_key ?? crypto.randomUUID(),
  }),
scrap: (payload: ScrapPayload) =>
  http.post<unknown, OperationRequest>('/asset-actions/scrap', {
    ...payload,
    idempotency_key: payload.idempotency_key ?? crypto.randomUUID(),
  }),
```

Keep repair methods mapped through `mapCommand()`.

- [ ] **Step 6: Implement the discriminated frontend result model**

```typescript
export type LifecycleResult =
  | { kind: 'request'; value: OperationRequest }
  | { kind: 'command'; value: AssetCommandResult }

export const lifecycleSuccessMessage = (result: LifecycleResult): string =>
  result.kind === 'request'
    ? `申请已提交，等待审批，单号 ${result.value.request_no}`
    : `已处理 ${result.value.updated_count} 件资产，命令号 ${result.value.command_no}`

export const lifecycleInvalidationKeys = (result: LifecycleResult): string[][] =>
  result.kind === 'request'
    ? [['operation-requests'], ['todo-center']]
    : [['assets'], ['dashboard']]
```

Wrap transfer/scrap mutation responses with `kind: 'request'` and repair responses with `kind: 'command'`. Use the helper in `onSuccess`, close/reset the form, and invalidate every returned query key. Replace visible copy that says transfer and scrap execute immediately with approval-oriented domain copy.

- [ ] **Step 7: Run API and frontend focused tests**

Working directory: `back`

Run: `.venv/bin/python -m pytest tests/test_asset_lifecycle_approval_api.py tests/test_asset_management_service.py -q`

Expected: all tests pass.

Working directory: `front`

Run: `node --experimental-strip-types --test src/features/operations/lifecycleResult.test.ts`

Expected: all tests pass.

- [ ] **Step 8: Commit Task 8**

```bash
git add back/app/api/asset_management.py back/app/services/asset_management_service.py back/tests/test_asset_lifecycle_approval_api.py back/tests/test_asset_management_service.py front/src/api/assetManagement.ts front/src/features/operations/Workflows.tsx front/src/features/operations/lifecycleResult.ts front/src/features/operations/lifecycleResult.test.ts
git commit -m "feat(asset): route lifecycle actions through approval"
```

## Task 9: Prove Approval, Failure, Retry, Termination, and Concurrency Paths

**Files:**
- Modify: `back/tests/test_asset_lifecycle_approval_api.py`
- Modify: `back/tests/test_asset_lifecycle_execution.py`
- Modify: production files only when a new test exposes a defect

- [ ] **Step 1: Add the sequential approval integration test**

Submit scrap with two approvers. Approve layer one and assert both assets remain unchanged and layer two becomes pending. Approve layer two and assert execution succeeds, locks disappear, lifecycle rows exist, and approval/execution statuses are `APPROVED / SUCCESS`.

Use `operation_service.approve_task()` so the test exercises the same service as the HTTP approval endpoint.

- [ ] **Step 2: Add rejection, withdrawal, and self-approval tests**

Add these assertions:

```python
with pytest.raises(BusinessException, match="不允许申请人自审"):
    asset_scrap_service.submit(payload, applicant.id)

operation_service.reject_task(task.id, approver.id, "资料不完整")
assert db.session.query(AssetBusinessLock).count() == 0
assert asset.status == AssetStatus.IDLE.value

operation_service.withdraw_request(operation.id, applicant.id, "业务取消")
assert db.session.query(AssetBusinessLock).count() == 0
assert asset.status == AssetStatus.IDLE.value
```

Use the actual service signatures in `operation_service.py`, including action idempotency keys where required.

- [ ] **Step 3: Add failed execution, retry, and termination tests**

Force snapshot drift by directly changing an asset version after submission. Final approval must produce `APPROVED / FAILED`, leave assets otherwise unchanged, and retain locks. Restore the expected state as the simulated administrator repair, call `operation_service.retry_request()`, and assert `SUCCESS` plus released locks.

Create a second failed request, call `operation_service.terminate_request()`, and assert `TERMINATED` plus released locks without asset mutation.

Create a dedicated all-scope recovery administrator with `approval:execution:retry` and `approval:execution:terminate`; use that actor for both service calls so the tests exercise the real permission boundary.

- [ ] **Step 4: Add concurrency coverage**

Use the existing threaded-app pattern from `test_approval_engine.py` and `test_operation_executor.py`. Two simultaneous approvals of the same final task must result in exactly one successful execution attempt and one set of lifecycle rows. The losing call may return the persisted completed request or a business conflict, but it must not execute again.

- [ ] **Step 5: Run the full lifecycle approval integration set**

Working directory: `back`

Run: `.venv/bin/python -m pytest tests/test_asset_lifecycle_submission.py tests/test_asset_lifecycle_execution.py tests/test_asset_lifecycle_approval_api.py -q`

Expected: all tests pass.

- [ ] **Step 6: Run nearby operation-kernel regressions**

Working directory: `back`

Run: `.venv/bin/python -m pytest tests/test_approval_engine.py tests/test_operation_executor.py tests/test_operation_api.py tests/test_asset_business_locks.py tests/test_asset_usage_return_integration.py -q`

Expected: all tests pass.

- [ ] **Step 7: Commit Task 9**

```bash
git add back/tests/test_asset_lifecycle_approval_api.py back/tests/test_asset_lifecycle_execution.py
git commit -m "test(asset): cover lifecycle approval recovery"
```

Before committing, inspect `git diff --cached --name-only`. If a failing Task 9 test required a production fix, stage only the exact production file changed for that fix in a separate commit; never stage the whole `back/app` tree.

## Task 10: Run Full Gates and Update Pilot Evidence

**Files:**
- Modify: `docs/testing/pilot/defect-register.md`
- Modify: `docs/testing/pilot/coverage-baseline.md`
- Modify: `docs/testing/pilot/2026-08-11-environment-automation-gate.md`

- [ ] **Step 1: Run backend lint and formatting checks**

Working directory: `back`

Run: `.venv/bin/ruff check .`

Expected: exit 0 with no findings.

Run: `.venv/bin/ruff format --check .`

Expected: exit 0 and all files already formatted.

- [ ] **Step 2: Run backend type checking**

Working directory: `back`

Run: `.venv/bin/mypy app/ config.py`

Expected: success with no issues.

- [ ] **Step 3: Run full backend business tests with coverage**

Working directory: `back`

Run: `.venv/bin/python -m pytest tests --ignore=tests/test_environment_contract.py --cov=app --cov-report=term-missing -q`

Expected: all business tests pass, total coverage does not fall below the current 89% baseline, and new submission/handler modules have focused branch coverage.

- [ ] **Step 4: Re-run the known environment contract separately**

Working directory: `back`

Run: `.venv/bin/python -m pytest tests/test_environment_contract.py -q`

Expected at the current repository baseline: 10 pass and the same 3 `PILOT-001` lock/toolchain failures remain. Any additional failure blocks completion of this feature.

- [ ] **Step 5: Run all frontend gates**

Working directory: `front`

Run: `npm run type-check`

Expected: exit 0.

Run: `npm run lint`

Expected: exit 0 with zero warnings.

Run: `npm test`

Expected: all tests pass, including `lifecycleResult.test.ts`.

Run: `npm run build`

Expected: production build succeeds.

- [ ] **Step 6: Update pilot evidence**

Change only `PILOT-009` evidence and aggregate counts affected by its status. Record:

- focused test command and pass count;
- full backend business pass count and coverage;
- frontend test/build results;
- migration upgrade/downgrade result;
- manual retest still required;
- unchanged `PILOT-001`, `PILOT-004`, and `PILOT-005` blockers.

Set `PILOT-009` to `READY_FOR_RETEST`, not `CLOSED`.

- [ ] **Step 7: Inspect the final diff and verify no unrelated work was staged**

Run: `git status --short`

Expected: implementation files and the three evidence documents are identifiable; pre-existing unrelated dirty files remain unstaged.

Run: `git diff --check`

Expected: no whitespace errors.

- [ ] **Step 8: Commit quality evidence**

```bash
git add docs/testing/pilot/defect-register.md docs/testing/pilot/coverage-baseline.md docs/testing/pilot/2026-08-11-environment-automation-gate.md
git commit -m "docs(test): record lifecycle approval gate"
```

## Execution Checkpoints

After Tasks 3, 5, 8, and 10, stop for a focused review before continuing:

- Task 3: approval candidate scope and backward compatibility.
- Task 5: immutable request construction and child disposition expansion.
- Task 8: public API no longer reaches direct mutation code.
- Task 10: complete verification evidence and remaining pilot blockers.

Do not mark `PILOT-009` closed until the manual two-person transfer and three-person scrap approval scenarios have been executed in the pilot environment and their audit records have been reviewed.
