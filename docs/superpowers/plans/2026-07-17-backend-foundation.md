# Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a maintainable Flask backend foundation with RBAC, scoped master data, asset-code reservation, a one-level stock-in approval workflow, formal asset records, audit history, and verified HTTP execution.

**Architecture:** Keep the repository's layered modular monolith (`api -> services -> repositories -> models`). Cross-domain workflows live in `stock_in_service`; repositories remain transaction-free; permission, approval, asset-code, asset, and audit modules expose narrow service methods. Approval state and execution state remain independent.

**Tech Stack:** Python 3.13, Flask 3, SQLAlchemy 2, Flask-SQLAlchemy, Marshmallow, Flask-JWT-Extended, Alembic/Flask-Migrate, pytest, Ruff, mypy, SQLite for fast tests and MySQL 8 for final concurrency/runtime verification.

---

## File map

New domain files:

```text
back/app/enums/__init__.py                  Shared persisted string enums
back/app/models/rbac.py                     Role, permission and association models
back/app/models/master_data.py              Organization, unit, source, location, category
back/app/models/workflow.py                 Operation request, stock-in, approval models
back/app/models/asset.py                    Sequence, reservation and formal asset
back/app/models/audit.py                    Operation log and asset lifecycle
back/app/repositories/rbac_repository.py    Permission and role queries
back/app/repositories/master_data_repository.py
back/app/repositories/workflow_repository.py
back/app/repositories/asset_repository.py
back/app/repositories/audit_repository.py
back/app/services/permission_service.py
back/app/services/organization_service.py
back/app/services/master_data_service.py
back/app/services/asset_code_service.py
back/app/services/approval_service.py
back/app/services/asset_service.py
back/app/services/audit_service.py
back/app/services/stock_in_service.py
back/app/schemas/rbac.py
back/app/schemas/master_data.py
back/app/schemas/stock_in.py
back/app/schemas/asset.py
back/app/api/rbac.py
back/app/api/organizations.py
back/app/api/master_data.py
back/app/api/stock_in.py
back/app/api/assets.py
back/app/security/current_user.py
back/migrations/versions/002_backend_foundation.py
```

Existing files modified only where required:

```text
back/app/models/user.py                     Add organization relation; remove legacy role field
back/app/models/__init__.py                 Import all models for SQLAlchemy metadata
back/app/repositories/__init__.py           Export repository singletons
back/app/services/__init__.py               Export service modules
back/app/schemas/__init__.py                Export new schemas
back/app/api/auth.py                        Login only; /api/v1 prefix
back/app/api/users.py                       Current user/list through permission service
back/app/api/__init__.py                    Register new blueprints
back/app/services/auth_service.py           DB-backed RBAC token identity
back/app/services/user_service.py           RBAC user serialization
back/tests/conftest.py                      Deterministic seed helpers and isolated transactions
```

No changes are planned for `Result`, error handlers, Flask app assembly, dependency versions, environment files, Docker files, or frontend files.

### Task 1: Persisted enums and RBAC models

**Files:**
- Create: `back/app/enums/__init__.py`
- Create: `back/app/models/rbac.py`
- Modify: `back/app/models/user.py`
- Modify: `back/app/models/__init__.py`
- Test: `back/tests/test_rbac_models.py`

- [ ] **Step 1: Write failing model tests**

Create tests that assert unique role/permission codes, explicit user-role rows, custom organization rows, and a user organization association. Use concrete records:

```python
def test_user_can_have_multiple_roles(db_session):
    user = User(username="rbac-user", password="x", enabled=True)
    admin = Role(code="SUPER_ADMIN", name="超级管理员", data_scope="ALL")
    viewer = Role(code="ASSET_VIEWER", name="资产查看", data_scope="SELF")
    db_session.add_all([user, admin, viewer])
    db_session.flush()
    db_session.add_all([UserRole(user_id=user.id, role_id=admin.id), UserRole(user_id=user.id, role_id=viewer.id)])
    db_session.flush()
    assert {row.role_id for row in db_session.query(UserRole).filter_by(user_id=user.id)} == {admin.id, viewer.id}
```

- [ ] **Step 2: Run the tests and confirm the missing-model failure**

Run: `cd back && pytest tests/test_rbac_models.py -q`

Expected: collection fails because `Role`, `Permission`, and association models do not exist.

- [ ] **Step 3: Add stable enums and models**

Define string enums for enabled status, data scope, approval status, execution status, code reservation status, asset status, request type, approval action, and audit action. Persist enum values in `String` columns rather than database-native enums.

Define explicit `Role`, `Permission`, `UserRole`, `RolePermission`, and `RoleDataScopeOrganization` models with unique constraints. Add nullable `organization_id` to `User`; remove runtime use of the legacy `role` attribute.

- [ ] **Step 4: Export models and run focused tests**

Run: `cd back && pytest tests/test_rbac_models.py -q`

Expected: all RBAC model tests pass.

### Task 2: RBAC repositories, permission service, and authentication

**Files:**
- Create: `back/app/repositories/rbac_repository.py`
- Create: `back/app/services/permission_service.py`
- Create: `back/app/security/current_user.py`
- Create: `back/app/schemas/rbac.py`
- Create: `back/app/api/rbac.py`
- Modify: `back/app/repositories/__init__.py`
- Modify: `back/app/services/auth_service.py`
- Modify: `back/app/services/user_service.py`
- Modify: `back/app/api/auth.py`
- Modify: `back/app/api/users.py`
- Modify: `back/app/security/__init__.py`
- Test: `back/tests/test_rbac.py`
- Test: `back/tests/test_auth.py`

- [ ] **Step 1: Write failing service and API tests**

Cover permission union, `ALL` precedence, organization-tree scope, custom scope, disabled users/roles, `/api/v1/auth/login`, `/api/v1/users/me`, role creation, permission assignment, and user-role assignment. Assert the public register endpoint is unavailable.

Use the public contract:

```python
assert permission_service.has_permission(user.id, "asset:view") is True
permission_service.require_organization_scope(user.id, organization.id)
response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
assert response.get_json()["code"] == 200
```

- [ ] **Step 2: Confirm tests fail against legacy role claims**

Run: `cd back && pytest tests/test_rbac.py tests/test_auth.py -q`

Expected: failures for missing RBAC service/API and legacy `/api/auth` paths.

- [ ] **Step 3: Implement repository queries and permission rules**

Implement these public service functions with DB reads on every request so role changes take effect without reissuing JWTs:

```python
get_user_permissions(user_id: int) -> set[str]
has_permission(user_id: int, permission_code: str) -> bool
require_permission(user_id: int, permission_code: str) -> None
accessible_organization_ids(user_id: int) -> set[int] | None  # None means ALL
require_organization_scope(user_id: int, organization_id: int) -> None
find_approval_candidates(permission_code: str, organization_id: int) -> list[int]
```

Multiple roles use permission and scope unions. Disabled roles and users contribute nothing. Field permission such as `asset:amount:view` is checked separately.

- [ ] **Step 4: Change JWT identity to the stable user ID**

Login uses `identity=str(user.id)` and does not embed authoritative role claims. `current_user_id()` parses and validates `get_jwt_identity()`. Remove the public register route while keeping password verification in `auth_service`.

- [ ] **Step 5: Add RBAC schemas and GET/POST-only APIs**

Implement `/api/v1/roles`, `/api/v1/permissions`, role update, permission assignment, and user-role assignment. All mutations use POST action URLs and `BusinessException` for failures.

- [ ] **Step 6: Run focused tests**

Run: `cd back && pytest tests/test_rbac.py tests/test_auth.py -q`

Expected: all focused tests pass.

### Task 3: Organization hierarchy

**Files:**
- Create: `back/app/models/master_data.py`
- Create: `back/app/repositories/master_data_repository.py`
- Create: `back/app/services/organization_service.py`
- Create: `back/app/schemas/master_data.py`
- Create: `back/app/api/organizations.py`
- Modify: package `__init__.py` files
- Test: `back/tests/test_organizations.py`

- [ ] **Step 1: Write failing hierarchy and API tests**

Cover string codes with leading zeroes, unique codes, tree output, top-level organization resolution, parent cycle rejection, immutable code, disable/enable, permission checks, and data-scope filtering.

- [ ] **Step 2: Verify expected failure**

Run: `cd back && pytest tests/test_organizations.py -q`

Expected: missing organization model/service/API failures.

- [ ] **Step 3: Implement organization model and repository**

Use `code`, `name`, `parent_id`, `status`, timestamps, and an integer version column. Repository methods include `find_by_code`, `find_children`, and ordered list queries.

- [ ] **Step 4: Implement explicit organization rules**

Public functions:

```python
create(payload: dict, actor_id: int) -> dict
update(organization_id: int, payload: dict, actor_id: int) -> dict
set_enabled(organization_id: int, enabled: bool, actor_id: int) -> dict
get(organization_id: int, actor_id: int) -> dict
tree(actor_id: int) -> list[dict]
get_top_level(organization_id: int) -> Organization
get_descendant_ids(organization_id: int) -> set[int]
```

Reject code changes, self-parenting, descendant-parenting, and disabling a missing record.

- [ ] **Step 5: Add API schemas and endpoints, then run tests**

Run: `cd back && pytest tests/test_organizations.py -q`

Expected: all organization tests pass.

### Task 4: Units, sources, locations, and asset categories

**Files:**
- Modify: `back/app/models/master_data.py`
- Modify: `back/app/repositories/master_data_repository.py`
- Create: `back/app/services/master_data_service.py`
- Modify: `back/app/schemas/master_data.py`
- Create: `back/app/api/master_data.py`
- Test: `back/tests/test_master_data.py`

- [ ] **Step 1: Write failing master-data tests**

Cover unique immutable codes, enabled-only selection, referenced records being disable-only, category parent cycles, category default unit, location sibling-name uniqueness, immutable location code, and `is_selectable` enforcement.

- [ ] **Step 2: Run and observe missing behavior**

Run: `cd back && pytest tests/test_master_data.py -q`

Expected: failures for missing models and endpoints.

- [ ] **Step 3: Implement focused models and services**

Models:

```text
Unit(code, name, status)
AssetSource(code, name, status)
AssetLocation(code, name, parent_id, status, is_selectable)
AssetCategory(code, name, parent_id, service_life_months, default_unit_id, status)
```

Use explicit `create_*`, `update_*`, `set_*_enabled`, list/tree, and `require_enabled_*` methods. Do not add a generic business CRUD service.

- [ ] **Step 4: Add GET/POST APIs and run tests**

Run: `cd back && pytest tests/test_master_data.py -q`

Expected: all master-data tests pass.

### Task 5: Workflow, asset, and audit persistence

**Files:**
- Create: `back/app/models/workflow.py`
- Create: `back/app/models/asset.py`
- Create: `back/app/models/audit.py`
- Create: `back/app/repositories/workflow_repository.py`
- Create: `back/app/repositories/asset_repository.py`
- Create: `back/app/repositories/audit_repository.py`
- Modify: model/repository exports
- Test: `back/tests/test_workflow_models.py`

- [ ] **Step 1: Write failing persistence-invariant tests**

Assert unique request number, unique asset code, unique sequence key, unique non-empty normalized serial number, one reservation per code, one task decision, and valid foreign-key relationships between request, stock-in item, asset, lifecycle, and audit rows.

- [ ] **Step 2: Confirm model failures**

Run: `cd back && pytest tests/test_workflow_models.py -q`

Expected: missing workflow/asset/audit model failures.

- [ ] **Step 3: Implement workflow models**

Create explicit models for operation request, stock-in request/items, approval steps/tasks/records. Store approval and execution statuses separately. A stock-in request references exactly one organization and owns one or more immutable item snapshots.

- [ ] **Step 4: Implement asset and audit models**

Create sequence/reservation/formal asset models with `Numeric(18, 2)` money, normalized serial, status strings, timestamps, and unique constraints. Create JSON-backed before/after audit payloads without storing secrets.

- [ ] **Step 5: Add narrow repositories and run tests**

Run: `cd back && pytest tests/test_workflow_models.py -q`

Expected: all persistence tests pass.

### Task 6: Asset-code reservation

**Files:**
- Create: `back/app/services/asset_code_service.py`
- Test: `back/tests/test_asset_codes.py`

- [ ] **Step 1: Write failing allocator tests**

Cover per-top-organization/per-category sequences, four-digit padding, expansion after 9999, multiple categories, multiple organizations, permanent voiding, and no reuse after rejection.

Expected examples:

```python
assert reserve(...).asset_code == "358466-10100-0001"
assert reserve(...).asset_code == "358466-10100-0002"
assert reserve(other_category, ...).asset_code == "358466-10200-0001"
```

- [ ] **Step 2: Verify tests fail**

Run: `cd back && pytest tests/test_asset_codes.py -q`

- [ ] **Step 3: Implement locked sequence allocation**

Use a row lock when selecting an existing sequence, a unique `(top_organization_id, category_id)` key when creating it, and unique asset-code reservations as the final concurrency guard. Group a request's items by category and allocate all codes inside its submission transaction.

Public methods:

```python
reserve(top_organization: Organization, category: AssetCategory, request_id: int) -> AssetCodeReservation
activate(reservation_id: int, asset_id: int) -> None
void_for_request(request_id: int) -> None
```

- [ ] **Step 4: Run allocator tests**

Run: `cd back && pytest tests/test_asset_codes.py -q`

Expected: all allocator tests pass.

### Task 7: Stock-in submission

**Files:**
- Create: `back/app/services/approval_service.py`
- Create: `back/app/services/audit_service.py`
- Create: `back/app/services/stock_in_service.py`
- Create: `back/app/schemas/stock_in.py`
- Create: `back/app/api/stock_in.py`
- Test: `back/tests/test_stock_in_submit.py`

- [ ] **Step 1: Write failing submission tests**

Cover required fields, same-organization batch restriction, enabled organization/category/unit/source/location, selectable location, active manager, non-negative amount, zero-amount reason, normalized serial uniqueness, missing approver, permission/data scope, all-or-nothing validation, code allocation, and approval-person snapshot.

- [ ] **Step 2: Confirm failures**

Run: `cd back && pytest tests/test_stock_in_submit.py -q`

- [ ] **Step 3: Implement request schemas**

Use nested Marshmallow schemas. The request contains `organization_id`, optional `remark`, and a non-empty `items` list. Each item contains the approved first-stage fields; cross-field validation enforces zero-amount reason.

- [ ] **Step 4: Implement submission orchestration**

Public method:

```python
submit(payload: dict, actor_id: int) -> dict
```

Validate the entire request before reserving codes. Find active approval candidates whose `stock-in:approve` permission and data scope cover the organization. Create request, item snapshots, reservations, one approval step, and one task per candidate in one transaction.

- [ ] **Step 5: Add POST and read APIs and run tests**

Run: `cd back && pytest tests/test_stock_in_submit.py -q`

Expected: all submission tests pass.

### Task 8: Approval decisions, execution, withdrawal, and retry

**Files:**
- Create: `back/app/services/asset_service.py`
- Modify: `back/app/services/approval_service.py`
- Modify: `back/app/services/stock_in_service.py`
- Modify: `back/app/api/stock_in.py`
- Test: `back/tests/test_stock_in_approval.py`

- [ ] **Step 1: Write failing workflow tests**

Cover authorized self-approval, unauthorized applicant approval, approve, reject-with-reason, applicant-only withdrawal, repeated actions, code voiding, formal asset creation, batch rollback, approval persistence when execution fails, retry authorization, and successful idempotent retry.

- [ ] **Step 2: Run and confirm missing workflow behavior**

Run: `cd back && pytest tests/test_stock_in_approval.py -q`

- [ ] **Step 3: Implement pure approval state transitions**

`approval_service` records decisions and task/step/request status. It never creates assets. Reject requires a non-empty opinion. Already-completed decisions return a deterministic result or raise a clear state error without adding duplicate records.

- [ ] **Step 4: Implement formal asset creation**

`asset_service.stock_in_request(request_id, actor_id)` revalidates immutable snapshots, creates every asset and lifecycle record, activates every reservation, and writes the operation log in one transaction.

- [ ] **Step 5: Implement the two-transaction approval orchestration**

`stock_in_service.approve` first commits the approval result, then calls formal execution. On execution exception it rolls back asset changes and stores `FAILED` in a fresh transaction. `retry` accepts only approved/failed requests and never changes snapshots.

- [ ] **Step 6: Implement reject and withdraw**

Both actions void reservations in their transaction and leave the formal asset table unchanged.

- [ ] **Step 7: Run workflow tests**

Run: `cd back && pytest tests/test_stock_in_approval.py -q`

Expected: all workflow tests pass.

### Task 9: Asset reads, lifecycle, audit, and field permissions

**Files:**
- Create: `back/app/schemas/asset.py`
- Create: `back/app/api/assets.py`
- Modify: `back/app/services/asset_service.py`
- Modify: `back/app/services/audit_service.py`
- Test: `back/tests/test_assets.py`

- [ ] **Step 1: Write failing read-policy tests**

Cover pagination, code/name/serial filters, organization data scope, `SELF` manager scope, disabled user denial, amount hidden without `asset:amount:view`, lifecycle visibility, and audit-list permission.

- [ ] **Step 2: Verify failures**

Run: `cd back && pytest tests/test_assets.py -q`

- [ ] **Step 3: Implement scoped repository queries and serialization**

Permission service calculates accessible organization IDs. Repository applies them in SQL, not after loading all assets. Serializer conditionally includes `original_amount` and `zero_amount_reason` only when the actor has amount-view permission.

- [ ] **Step 4: Add asset/lifecycle/audit GET APIs and run tests**

Run: `cd back && pytest tests/test_assets.py -q`

Expected: all read-policy tests pass.

### Task 10: Blueprint registration and Alembic migration

**Files:**
- Modify: `back/app/api/__init__.py`
- Modify: package exports
- Create: `back/migrations/versions/002_backend_foundation.py`
- Test: `back/tests/test_migrations.py`

- [ ] **Step 1: Write migration contract tests**

Assert model metadata can create every table and the migration file declares `revision = "002"`, `down_revision = "001"`. Add a subprocess migration test against a temporary SQLite database that upgrades from base to head.

- [ ] **Step 2: Generate and normalize migration**

Create one append-only migration named `002_backend_foundation.py`. It creates RBAC and domain tables, backfills `ADMIN`/`USER` roles from `users.role`, associates existing users, and removes the legacy role column using Alembic batch operations compatible with SQLite.

- [ ] **Step 3: Register all `/api/v1` blueprints**

Keep `/api/hello` only as existing scaffold health/sample behavior. Business APIs use `/api/v1` exclusively.

- [ ] **Step 4: Run migration and API registration tests**

Run: `cd back && pytest tests/test_migrations.py -q`

Expected: clean upgrade to head and all blueprint paths present.

### Task 11: Full static, automated, and runtime verification

**Files:**
- Create: `back/tests/test_stock_in_e2e.py`
- Modify only implementation/test files needed for verified defects

- [ ] **Step 1: Add a real HTTP end-to-end test**

The test logs in, creates master data, assigns permissions, submits a stock-in request, approves it, queries the asset, then verifies lifecycle and audit rows through HTTP.

- [ ] **Step 2: Run the complete backend gate**

Run:

```bash
cd back
ruff check .
ruff format --check .
mypy app/ config.py
pytest
```

Expected: zero warnings/errors and all tests pass.

- [ ] **Step 3: Verify a clean migration and live Flask process**

Use a temporary development database, run `FLASK_APP=manage.py flask db upgrade`, start the backend, call liveness/readiness, then perform login and the stock-in workflow with HTTP requests. Record exact commands and responses for the reviewer.

- [ ] **Step 4: Verify MySQL-specific behavior when Docker MySQL is available**

Run the migration and concurrent code-allocation test against MySQL 8. If the current Compose configuration does not provide MySQL, record this as an explicit review blocker rather than modifying unrelated Docker files in this feature.

### Task 12: Independent read-only review and repair loop

**Files:**
- Review only; reviewer must not modify files

- [ ] **Step 1: Dispatch the independent reviewer**

Give the reviewer the approved design, implementation plan, current diff, test commands, and runtime evidence. Require findings in six categories: requirements completeness, logic correctness, edge cases, code quality, test coverage, actual runtime.

- [ ] **Step 2: Convert findings into the main-thread repair checklist**

Each finding must include severity, file/line or command evidence, impact, and verification criteria. Main thread owns every code change.

- [ ] **Step 3: Repair and run the complete gate**

Apply focused fixes using failing tests first, then rerun Ruff, formatting, mypy, pytest, migration, and live HTTP checks.

- [ ] **Step 4: Send the same reviewer a re-verification request**

Repeat until the reviewer reports no blocking findings. If an external dependency prevents verification, record the repeated blocker, completed checks, and residual risk explicitly.
