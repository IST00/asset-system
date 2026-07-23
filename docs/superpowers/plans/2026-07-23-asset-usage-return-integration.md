# Asset Usage and Return Integration Plan

**Goal:** Wire the completed usage/return feature into the Flask application and database without coupling it to unfinished operation features.

**Architecture:** Keep feature behavior in existing leaf modules. Public aggregation files only expose/register concrete components. Add one immutable Alembic revision dedicated to the three usage/return tables and two permissions.

## Task 1: Lock the integration contract with tests

- [ ] Add tests for model exports, formal routes, dev/test-only mock routes, and all four handler registrations.
- [ ] Add migration revision, schema/index/foreign-key, permission-role mapping, and downgrade tests.
- [ ] Run the focused tests and confirm they fail only because integration is absent.

## Task 2: Register runtime components

- [ ] Export the three feature models from `app.models`.
- [ ] Register usage and return Blueprints for every Profile.
- [ ] Register local Feishu Blueprint only when `app.testing` or `app.debug` is true.
- [ ] Idempotently register the four feature handlers beside `StockInHandler`.
- [ ] Run focused integration and API tests.

## Task 3: Add revision 005

- [ ] Create `005_asset_usage_return.py` after revision 004.
- [ ] Create three tables with model-equivalent columns, JSON snapshots, foreign keys, and indexes.
- [ ] Seed `asset:usage:manage` and `asset:return:self` and grant built-in roles.
- [ ] Implement dependency-safe downgrade.
- [ ] Run focused migration upgrade/downgrade tests.

## Task 4: Verify the integrated application

- [ ] Run SQLite clean upgrade, downgrade to 004, re-upgrade, and schema comparison.
- [ ] Run Ruff, format check, mypy, conventions guard, and full pytest.
- [ ] Start Flask and perform HTTP smoke checks.
- [ ] If permitted by the configured account, run upgrade/downgrade in an isolated temporary schema on the configured external MySQL server.

## Task 5: Independent review loop

- [ ] Ask an independent agent to review requirements, logic, boundaries, quality, tests, and runtime evidence without editing code.
- [ ] Convert findings into a repair checklist and fix them in the main thread.
- [ ] Ask the same reviewer to re-run verification until PASS or a concrete external blocker remains.
