# Asset Operation Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved asset-operation and approval foundation, migrate stock-in onto it without API regressions, and freeze a safe baseline for parallel feature development.

**Architecture:** Extend the existing layered modular monolith with an explicit operation kernel (`operation_service`, locks, executor, handler registry) and a bounded approval engine (versioned flows, sequential layers, OR/AND signing). Feature services retain typed detail tables and delegate only lifecycle concerns to the kernel. Shared aggregators and Alembic remain main-thread owned.

**Tech Stack:** Python 3.13, Flask 3, SQLAlchemy 2, Flask-SQLAlchemy, Marshmallow, Flask-JWT-Extended, Alembic, pytest, Ruff, mypy, SQLite and MySQL 8.

---

## File map

New shared files:

```text
back/app/models/operation.py
back/app/models/approval_flow.py
back/app/repositories/operation_repository.py
back/app/repositories/approval_flow_repository.py
back/app/services/operation_service.py
back/app/services/asset_lock_service.py
back/app/services/operation_executor.py
back/app/services/approval_flow_service.py
back/app/services/approval_engine.py
back/app/operations/__init__.py
back/app/operations/registry.py
back/app/operations/providers.py
back/app/operations/stock_in_handler.py
back/app/schemas/operation.py
back/app/schemas/approval_flow.py
back/app/api/operations.py
back/app/api/approval_flows.py
back/migrations/versions/003_operation_foundation.py
back/tests/test_operation_models.py
back/tests/test_approval_flow_config.py
back/tests/test_approval_engine.py
back/tests/test_asset_business_locks.py
back/tests/test_operation_executor.py
back/tests/test_approval_providers.py
back/tests/test_operation_api.py
back/tests/test_stock_in_foundation_compat.py
```

Existing shared files modified only by the main thread:

```text
back/app/enums/__init__.py
back/app/models/__init__.py
back/app/models/asset.py
back/app/models/workflow.py
back/app/repositories/__init__.py
back/app/repositories/workflow_repository.py
back/app/services/__init__.py
back/app/services/stock_in_service.py
back/app/services/approval_service.py
back/app/api/__init__.py
back/tests/conftest.py
back/tests/test_migrations.py
```

## Task 1: Characterize the existing stock-in contract

**Files:**
- Create: `back/tests/test_stock_in_foundation_compat.py`
- Read: `back/app/api/stock_in.py`
- Read: `back/app/services/stock_in_service.py`

- [ ] **Step 1: Write compatibility tests before refactoring**

Add tests that use the current HTTP routes and assert:

```python
def test_stock_in_contract_survives_operation_foundation(client, stock_in_context):
    submitted = submit_stock_in(client, stock_in_context)
    assert submitted["approval_status"] == "PENDING"
    assert submitted["execution_status"] == "NOT_STARTED"
    assert submitted["items"][0]["asset_code"].endswith("-0001")

    approved = approve_stock_in(client, stock_in_context, submitted["id"])
    assert approved["approval_status"] == "APPROVED"
    assert approved["execution_status"] == "SUCCESS"
```

Cover list/detail permissions, self-approval, rejection, withdrawal, execution failure, retry, amount-field protection, serial reservation release, idempotent repeated approval, lifecycle and audit output.

- [ ] **Step 2: Run compatibility tests against the current implementation**

Run: `cd back && .venv/bin/python -m pytest tests/test_stock_in_foundation_compat.py -q`

Expected: PASS. These are characterization tests; they establish the no-regression baseline rather than a RED test.

- [ ] **Step 3: Record the current route map**

In the test, assert the six existing stock-in mutation/read routes remain GET/POST-only. Do not snapshot unrelated Flask routes.

## Task 2: Add shared enums and asset-usage contract

**Files:**
- Modify: `back/app/enums/__init__.py`
- Modify: `back/app/models/asset.py`
- Test: `back/tests/test_operation_models.py`

- [ ] **Step 1: Write failing enum and model tests**

Assert these persisted values exist:

```python
ApprovalChannel: INTERNAL, FEISHU, DIRECT
SignMode: OR_SIGN, AND_SIGN
AssigneeType: USER, ROLE
FlowStatus: DRAFT, PUBLISHED, DISABLED
RuntimeTaskStatus: WAITING, PENDING, APPROVED, REJECTED, WITHDRAWN
ExecutionAttemptStatus: PROCESSING, SUCCESS, FAILED
ExecutionTriggerType: APPROVAL, RETRY
UsageType: PERSONAL, PUBLIC
```

Assert `Asset` exposes nullable `usage_type`, `holder_user_id`, `public_object_id`, `usage_department_id`, `parent_asset_id`, and retains the existing optimistic `version`.

- [ ] **Step 2: Verify RED**

Run: `cd back && .venv/bin/python -m pytest tests/test_operation_models.py -q`

Expected: FAIL for missing enums and columns.

- [ ] **Step 3: Implement only the declared enums and fields**

Add a `PublicUsageObject` model with immutable unique code, unique name and enabled/disabled status. Foreign keys from `Asset` use `RESTRICT`/`SET NULL` according to the design; do not add login fields to public objects.

- [ ] **Step 4: Verify GREEN**

Run: `cd back && .venv/bin/python -m pytest tests/test_operation_models.py -q`

Expected: all Task 2 tests pass.

## Task 3: Add operation-kernel persistence

**Files:**
- Create: `back/app/models/operation.py`
- Modify: `back/app/models/workflow.py`
- Modify: `back/app/models/__init__.py`
- Test: `back/tests/test_operation_models.py`

- [ ] **Step 1: Write failing persistence-invariant tests**

Cover:

```text
OperationRequestAsset: unique(operation_request_id, asset_id)
AssetBusinessLock: unique(asset_id)
OperationExecutionAttempt: unique(operation_request_id, attempt_no)
ExternalApprovalEvent: unique(provider, external_event_id)
OperationRequest: unique(applicant_id, operation_type, idempotency_key)
```

Assert immutable snapshots use JSON plus explicit code/name/status/version columns. Assert all foreign keys point to existing requests/assets/users.

- [ ] **Step 2: Verify RED**

Run: `cd back && .venv/bin/python -m pytest tests/test_operation_models.py -q`

- [ ] **Step 3: Implement kernel models**

Add the models and extend `OperationRequest` with:

```python
parent_request_id: int | None
approval_channel: str
approval_flow_version_id: int | None
external_instance_id: str | None
idempotency_key: str | None
submitted_at: datetime | None
approved_at: datetime | None
executed_at: datetime | None
terminated_at: datetime | None
terminated_by: int | None
termination_reason: str | None
```

Keep `flow_version` temporarily for migration compatibility; remove runtime use after Task 12.

- [ ] **Step 4: Verify model tests**

Run: `cd back && .venv/bin/python -m pytest tests/test_operation_models.py -q`

Expected: PASS.

## Task 4: Add versioned approval-flow persistence

**Files:**
- Create: `back/app/models/approval_flow.py`
- Modify: `back/app/models/workflow.py`
- Modify: `back/app/models/__init__.py`
- Test: `back/tests/test_operation_models.py`

- [ ] **Step 1: Write failing flow-model tests**

Assert:

```text
ApprovalFlowDefinition: unique operation_type
ApprovalFlowVersion: unique(flow_definition_id, version_no)
ApprovalFlowLayer: unique(flow_version_id, level_no)
ApprovalFlowAssigneeRule: unique(layer_id, assignee_type, assignee_id)
```

Runtime changes:

- `ApprovalStep` stores `flow_layer_id`, `sign_mode` and `WAITING/PENDING/...` status.
- `ApprovalTask` stores snapshotted approver ID and runtime status.
- Replace `ApprovalRecord` unique-on-step with unique-on-task so AND_SIGN can record every approver exactly once.

- [ ] **Step 2: Verify RED**

Run: `cd back && .venv/bin/python -m pytest tests/test_operation_models.py -q`

- [ ] **Step 3: Implement flow models and corrected runtime constraints**

Use string persisted enums, timestamps and integer versions. Do not add a generic expression or script column.

- [ ] **Step 4: Verify GREEN**

Run: `cd back && .venv/bin/python -m pytest tests/test_operation_models.py -q`

## Task 5: Add explicit repositories

**Files:**
- Create: `back/app/repositories/operation_repository.py`
- Create: `back/app/repositories/approval_flow_repository.py`
- Modify: `back/app/repositories/workflow_repository.py`
- Modify: `back/app/repositories/__init__.py`
- Test: `back/tests/test_operation_models.py`

- [ ] **Step 1: Write failing repository tests**

Specify these methods:

```python
operation_request_asset_repository.find_by_request(request_id: int)
asset_business_lock_repository.acquire_rows(rows: list[AssetBusinessLock])
asset_business_lock_repository.release_for_request(request_id: int)
execution_attempt_repository.next_attempt_no(request_id: int) -> int
approval_flow_repository.find_published(operation_type: str)
approval_flow_repository.next_version_no(flow_id: int) -> int
approval_flow_repository.load_version_graph(version_id: int)
approval_step_repository.find_current_for_update(request_id: int)
approval_task_repository.find_for_update(step_id: int, actor_id: int)
```

- [ ] **Step 2: Verify RED**

Run: `cd back && .venv/bin/python -m pytest tests/test_operation_models.py -q`

- [ ] **Step 3: Implement query-only repositories**

Repositories may flush but never commit and never raise `BusinessException`. Use `with_for_update()` for current runtime rows and deterministic ordering by level/task ID.

- [ ] **Step 4: Verify GREEN**

Run: `cd back && .venv/bin/python -m pytest tests/test_operation_models.py -q`

## Task 6: Implement approval-flow configuration and publication

**Files:**
- Create: `back/app/services/approval_flow_service.py`
- Create: `back/app/schemas/approval_flow.py`
- Create: `back/app/api/approval_flows.py`
- Test: `back/tests/test_approval_flow_config.py`

- [ ] **Step 1: Write failing service/API tests**

Cover draft creation, contiguous levels starting at 1, OR/AND validation, non-empty USER/ROLE assignees, enabled users/roles, publish creating an immutable version, duplicate published operation type handling, disable/restore, permissions and GET/POST-only routes.

Public service signatures:

```python
create_definition(operation_type: str, name: str, actor_id: int) -> dict
save_draft(flow_id: int, payload: dict, actor_id: int) -> dict
publish(version_id: int, actor_id: int) -> dict
set_enabled(flow_id: int, enabled: bool, actor_id: int) -> dict
get_published(operation_type: str) -> ApprovalFlowVersion
```

- [ ] **Step 2: Verify RED**

Run: `cd back && .venv/bin/python -m pytest tests/test_approval_flow_config.py -q`

- [ ] **Step 3: Implement minimal configuration APIs**

Routes:

```text
GET  /api/v1/approval-flows
GET  /api/v1/approval-flows/{id}
POST /api/v1/approval-flows
POST /api/v1/approval-flows/{id}/drafts
POST /api/v1/approval-flow-versions/{id}/publish
POST /api/v1/approval-flows/{id}/disable
POST /api/v1/approval-flows/{id}/enable
```

Use `approval:flow:view/edit/publish/disable` permissions. Every publication writes an operation log with before/after configuration.

- [ ] **Step 4: Verify GREEN**

Run: `cd back && .venv/bin/python -m pytest tests/test_approval_flow_config.py -q`

## Task 7: Implement multi-layer OR/AND approval runtime

**Files:**
- Create: `back/app/services/approval_engine.py`
- Modify: `back/app/services/approval_service.py`
- Test: `back/tests/test_approval_engine.py`

- [ ] **Step 1: Write failing runtime tests**

Cover:

- submission snapshots all layers and role members using organization scope;
- missing approver rejects submission;
- later layers start WAITING;
- OR_SIGN first approval completes the layer and withdraws remaining tasks;
- AND_SIGN requires every task;
- any rejection ends the request and later layers;
- next layer activates only after previous approval;
- self-approval configuration is enforced in the backend;
- flow edits after submission do not alter runtime tasks;
- concurrent decisions produce one valid task/layer/request transition.

Public signatures:

```python
initialize(operation: OperationRequest, flow_version_id: int, organization_id: int) -> None
approve(operation_request_id: int, actor_id: int, opinion: str | None) -> ApprovalOutcome
reject(operation_request_id: int, actor_id: int, opinion: str) -> ApprovalOutcome
withdraw(operation_request_id: int, actor_id: int, reason: str | None) -> None
```

- [ ] **Step 2: Verify RED**

Run: `cd back && .venv/bin/python -m pytest tests/test_approval_engine.py -q`

- [ ] **Step 3: Implement CAS-based runtime**

Use row locks plus status/version CAS. `ApprovalOutcome` contains `request_approved`, `request_rejected`, and `next_layer_activated`; it does not execute feature business logic.

- [ ] **Step 4: Run runtime and existing approval tests**

Run: `cd back && .venv/bin/python -m pytest tests/test_approval_engine.py tests/test_stock_in_approval.py -q`

Expected: new runtime passes; legacy tests may remain on the compatibility adapter until Task 12.

## Task 8: Implement asset business locking and operation submission

**Files:**
- Create: `back/app/services/asset_lock_service.py`
- Create: `back/app/services/operation_service.py`
- Test: `back/tests/test_asset_business_locks.py`

- [ ] **Step 1: Write failing lock and submission tests**

Cover sorted multi-asset locking, unique conflict mapped to safe `BusinessException`, lock metadata, immutable asset snapshots, idempotency key replay, all-or-nothing validation, release on rejection/withdrawal, retention on execution failure and release on success/termination.

Public signatures:

```python
create_request(
    *, operation_type: str, applicant_id: int, approval_channel: str,
    organization_id: int, assets: list[Asset], idempotency_key: str | None,
    parent_request_id: int | None = None,
) -> OperationRequest
release_locks(operation_request_id: int) -> None
get_by_idempotency_key(actor_id: int, operation_type: str, key: str) -> OperationRequest | None
```

- [ ] **Step 2: Verify RED**

Run: `cd back && .venv/bin/python -m pytest tests/test_asset_business_locks.py -q`

- [ ] **Step 3: Implement lock acquisition and snapshot creation**

Acquire rows in ascending asset ID order. Catch only the named lock uniqueness conflict; rollback the whole request and return the conflicting asset/request information without SQL text.

- [ ] **Step 4: Verify concurrency with independent transactions**

Add a file-SQLite two-thread test where both requests target the same asset. Assert one succeeds, one receives a business conflict, and only one current lock exists.

Run: `cd back && .venv/bin/python -m pytest tests/test_asset_business_locks.py -q`

## Task 9: Implement handler registry and transactional executor

**Files:**
- Create: `back/app/operations/__init__.py`
- Create: `back/app/operations/registry.py`
- Create: `back/app/services/operation_executor.py`
- Test: `back/tests/test_operation_executor.py`

- [ ] **Step 1: Write failing registry/executor tests**

Define:

```python
class OperationHandler(Protocol):
    operation_type: str
    def revalidate_for_execution(self, operation_request_id: int) -> None: ...
    def execute(self, operation_request_id: int, actor_id: int) -> None: ...
```

Test duplicate registration, missing handler, approved-only execution, one execution attempt per trigger, batch rollback, safe error persistence, successful idempotency, failed retry and termination.

- [ ] **Step 2: Verify RED**

Run: `cd back && .venv/bin/python -m pytest tests/test_operation_executor.py -q`

- [ ] **Step 3: Implement executor transaction boundaries**

`execute()` creates/commits the PROCESSING attempt only as part of the execution transaction. On failure it rolls back feature changes, then persists FAILED in a fresh transaction while retaining locks. On success it marks request/attempt SUCCESS and releases locks in the same transaction.

Public signatures:

```python
execute(operation_request_id: int, actor_id: int, trigger_type: str) -> OperationRequest
retry(operation_request_id: int, actor_id: int) -> OperationRequest
terminate(operation_request_id: int, actor_id: int, reason: str) -> OperationRequest
```

- [ ] **Step 4: Verify GREEN**

Run: `cd back && .venv/bin/python -m pytest tests/test_operation_executor.py -q`

## Task 10: Add approval providers and callback idempotency

**Files:**
- Create: `back/app/operations/providers.py`
- Create: `back/app/services/approval_provider_service.py`
- Test: `back/tests/test_approval_providers.py`

- [ ] **Step 1: Write failing provider tests**

Cover deterministic local FEISHU submission, confirmation, rejection, withdrawal, urge, external instance persistence, duplicate callback event, stale callback state and DIRECT confirmation.

- [ ] **Step 2: Verify RED**

Run: `cd back && .venv/bin/python -m pytest tests/test_approval_providers.py -q`

- [ ] **Step 3: Implement narrow provider registry**

Provide `LocalFeishuApprovalProvider` only. It generates a stable local external instance ID and accepts test callbacks through the service layer. Do not call real Feishu or introduce HTTP dependencies in this task.

- [ ] **Step 4: Verify GREEN**

Run: `cd back && .venv/bin/python -m pytest tests/test_approval_providers.py -q`

## Task 11: Add common operation read/action APIs

**Files:**
- Create: `back/app/schemas/operation.py`
- Create: `back/app/api/operations.py`
- Modify: `back/app/api/__init__.py`
- Test: `back/tests/test_operation_api.py`

- [ ] **Step 1: Write failing API tests**

Routes:

```text
GET  /api/v1/operation-requests
GET  /api/v1/operation-requests/{id}
GET  /api/v1/approval-tasks/my
POST /api/v1/approval-tasks/{id}/approve
POST /api/v1/approval-tasks/{id}/reject
POST /api/v1/operation-requests/{id}/withdraw
POST /api/v1/operation-requests/{id}/retry
POST /api/v1/operation-requests/{id}/terminate
```

Cover permission/data-scope SQL filters, SELF applicant access, amount-field protection in snapshots, actor ownership, rejection/termination reasons, and GET/POST-only route guards.

- [ ] **Step 2: Verify RED**

Run: `cd back && .venv/bin/python -m pytest tests/test_operation_api.py -q`

- [ ] **Step 3: Implement thin blueprints and explicit schemas**

Blueprints perform only Marshmallow load/dump, JWT and service calls. Common service responses include request, asset snapshots, approval timeline and execution attempts; feature details remain available through feature APIs.

- [ ] **Step 4: Verify GREEN**

Run: `cd back && .venv/bin/python -m pytest tests/test_operation_api.py -q`

## Task 12: Migrate stock-in onto the kernel

**Files:**
- Create: `back/app/operations/stock_in_handler.py`
- Modify: `back/app/services/stock_in_service.py`
- Modify: `back/app/services/asset_service.py`
- Modify: `back/app/services/approval_service.py`
- Modify: `back/tests/conftest.py`
- Test: `back/tests/test_stock_in_foundation_compat.py`
- Test: existing `back/tests/test_stock_in_*.py`

- [ ] **Step 1: Write the new failing integration assertion**

After submit, assert the stock-in request references a published flow version and has runtime steps/tasks created by `approval_engine`. After approval, assert exactly one execution attempt exists with trigger `APPROVAL`.

- [ ] **Step 2: Verify RED**

Run: `cd back && .venv/bin/python -m pytest tests/test_stock_in_foundation_compat.py -q`

- [ ] **Step 3: Add StockInHandler**

Move execution-only orchestration behind:

```python
class StockInHandler:
    operation_type = "STOCK_IN"
    def revalidate_for_execution(self, operation_request_id: int) -> None: ...
    def execute(self, operation_request_id: int, actor_id: int) -> None: ...
```

The handler calls narrow asset-code, asset and audit services; it does not commit.

- [ ] **Step 4: Change stock-in submission and approval delegation**

Submission keeps all existing field validation and code reservations, selects the published STOCK_IN flow, and calls `approval_engine.initialize`. Approval/rejection/withdraw/retry delegate to common services while preserving existing stock-in response DTOs and route paths.

- [ ] **Step 5: Register handler in the main-owned registry**

Use one explicit registration from application assembly. Do not let importing the handler mutate global state implicitly.

- [ ] **Step 6: Run all stock-in tests**

Run: `cd back && .venv/bin/python -m pytest tests/test_stock_in_foundation_compat.py tests/test_stock_in_submit.py tests/test_stock_in_approval.py tests/test_stock_in_e2e.py -q`

Expected: all legacy and new integration tests pass.

## Task 13: Add append-only Alembic migration 003

**Files:**
- Create: `back/migrations/versions/003_operation_foundation.py`
- Modify: `back/tests/test_migrations.py`

- [ ] **Step 1: Write failing migration contract tests**

Assert `revision = "003"`, `down_revision = "002"`, all new tables/columns/indexes exist after upgrade, runtime approval-record uniqueness is migrated from step to task, built-in STOCK_IN flow/version/layer/role rule exists, and downgrade restores the exact 002 schema/data semantics.

- [ ] **Step 2: Verify RED**

Run: `cd back && .venv/bin/python -m pytest tests/test_migrations.py -q`

- [ ] **Step 3: Generate then normalize migration**

Generate from merged metadata, rename to `003_operation_foundation.py`, and manually verify:

- MySQL-safe foreign-key/index order;
- nullable backfill before non-null constraints;
- existing stock-in operations map to a valid built-in flow version;
- existing approval records survive constraint replacement;
- downgrade deletes only 003 data and restores 002 columns/constraints.

- [ ] **Step 4: Run clean upgrade/downgrade**

Run: `cd back && .venv/bin/python -m pytest tests/test_migrations.py -q`

Expected: clean SQLite `base -> head -> 002` and data assertions pass.

## Task 14: Complete verification and independent review loop

**Files:**
- Modify only files required by verified defects

- [ ] **Step 1: Run the complete backend gate**

```bash
cd back
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app/ config.py
.venv/bin/python -m pytest -q
```

Expected: zero lint/type errors and all tests pass.

- [ ] **Step 2: Run convention and migration checks**

```bash
git diff --check
bash scripts/guard-conventions.sh
docker compose config --quiet
```

Scan production files for Redis, Blueprint model/db access, and PUT/DELETE/PATCH routes.

- [ ] **Step 3: Run actual application verification**

Create a temporary database, upgrade to 003, verify liveness/readiness, log in, submit/approve stock-in, query asset/lifecycle/audit, then exercise an internal two-layer OR/AND fixture and a simulated FEISHU confirmation. Run MySQL 8 migration and concurrency tests when Docker permissions allow it; otherwise record the external blocker.

- [ ] **Step 4: Dispatch independent read-only reviewer**

Require findings in six categories: requirements completeness, logic correctness, edge cases, code quality, test coverage and actual runtime. Reviewer must not edit files.

- [ ] **Step 5: Repair and re-verify**

Main thread converts findings into a severity-ordered checklist, writes failing tests, applies focused fixes, reruns the complete gate and sends the same reviewer a re-verification request. Repeat until PASS or a repeated external blocker is explicitly documented.

## Commit policy

After each green task, create a focused Conventional Commit if the Git approval service is available. If commit is rejected by the existing external 401 approval failure, preserve the changes in the current feature branch, report the blocker and continue only after verifying the exact diff; never bypass hooks or alter Git internals.
