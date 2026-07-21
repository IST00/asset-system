# External MySQL Compose Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run only application services in Compose while securely injecting the externally managed MySQL configuration before Python starts.

**Architecture:** Compose reads an untracked deployment dotenv selected by `BACK_ENV_FILE` and injects it into the backend process. Tracked production dotenv remains a placeholder template, and all dotenv files are excluded from the backend image. The pre-existing `config.py` profile-loading defect is recorded for a separate scaffolding PR because project policy forbids mixing that core change into this branch.

**Tech Stack:** Docker Compose, Flask profile configuration, pytest.

---

## File map

- Modify `back/tests/test_no_redis_configuration.py`: enforce Compose and secret-boundary contracts.
- Modify `docker-compose.yml`: use external `env_file` and keep only backend/frontend.
- Modify `.gitignore`: ignore `back/.env.deploy`.
- Modify `back/.dockerignore`: exclude dotenv files from the image context.
- Replace `back/.env.prod`: keep only safe production placeholders.
- Preserve local credentials in ignored `back/.env.deploy` before sanitizing the tracked template.

### Task 1: Secure the external-database Compose boundary

**Files:**
- Modify: `back/tests/test_no_redis_configuration.py`
- Modify: `docker-compose.yml`
- Modify: `.gitignore`
- Modify: `back/.dockerignore`
- Modify: `back/.env.prod`
- Create locally, ignored: `back/.env.deploy`

- [ ] **Step 1: Extend the failing deployment contract tests**

The tests must assert:

```python
def test_compose_uses_external_database_configuration():
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "\n  mysql:" not in compose
    assert "\n  redis:" not in compose
    assert "mysql_data" not in compose
    for key in (
        "DB_URL:", "DB_HOST:", "DB_PORT:", "DB_NAME:", "DB_USER:",
        "DB_PASSWORD:", "JWT_SECRET:", "SECRET_KEY:",
    ):
        assert key not in compose
    assert "env_file:" in compose
    assert "${BACK_ENV_FILE:-./back/.env.deploy}" in compose
    assert "FLASK_ENV: ${APP_ENV:-prod}" in compose
    assert "depends_on:\n      - back" in compose


def test_deployment_secrets_are_not_tracked_or_copied_into_image():
    gitignore = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (BACKEND_ROOT / ".dockerignore").read_text(encoding="utf-8")
    production_env = (BACKEND_ROOT / ".env.prod").read_text(encoding="utf-8")

    assert "back/.env.deploy" in gitignore
    assert ".env*" in dockerignore
    assert "CHANGE_ME_IN_DEPLOYMENT" in production_env
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
cd back
.venv/bin/python -m pytest tests/test_no_redis_configuration.py -q
```

Expected: FAIL because Compose lacks `env_file`, ignore rules are absent, and the tracked production dotenv is not placeholder-only.

- [ ] **Step 3: Preserve local configuration and implement the boundary**

Before sanitizing the tracked template, move its current contents to ignored
`back/.env.deploy`. Then:

```yaml
services:
  back:
    build: ./back
    env_file:
      - ${BACK_ENV_FILE:-./back/.env.deploy}
    environment:
      FLASK_ENV: ${APP_ENV:-prod}
    ports:
      - "8080:8080"
      - "8081:8081"

  front:
    build: ./front
    ports:
      - "80:80"
    depends_on:
      - back
```

Add `back/.env.deploy` to `.gitignore`, add `.env*` to
`back/.dockerignore`, and replace `back/.env.prod` values with
`CHANGE_ME_IN_DEPLOYMENT` placeholders.

- [ ] **Step 4: Verify GREEN and rendered Compose structure**

Run:

```bash
cd back
.venv/bin/python -m pytest tests/test_no_redis_configuration.py -q
cd ..
docker compose config --quiet
docker compose config --services
git check-ignore back/.env.deploy
```

Expected: tests pass; Compose services are exactly `back` and `front`; the
deployment file is ignored.

- [ ] **Step 5: Run the complete gate and independent review**

```bash
cd back
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app/ config.py
.venv/bin/python -m pytest -q
cd ..
git diff --check
docker compose config --quiet
```

The independent reviewer must validate requirements, correctness, edge cases,
code quality, test coverage, and actual Compose rendering without editing code.

- [ ] **Step 6: Commit the focused current-branch change**

```bash
git add .gitignore back/.dockerignore back/.env.prod docker-compose.yml \
  back/tests/test_no_redis_configuration.py \
  docs/superpowers/specs/2026-07-19-external-mysql-compose-design.md \
  docs/superpowers/plans/2026-07-19-external-mysql-compose.md
git commit -m "fix: inject external mysql configuration"
```

If the approval-service 401 prevents committing, leave verified files staged
and report the external blocker without bypassing hooks.

### Task 2: Correct profile loading in a separate scaffolding PR

**Files:**
- Modify in separate branch: `back/config.py`
- Modify in separate branch: relevant fresh-process configuration tests

- [ ] **Step 1: Create a branch/worktree from the latest integration base**

Use a `fix/*` branch dedicated to the scaffolding-tagged PR. Do not mix the
`config.py` change into the current feature branch.

- [ ] **Step 2: Write fresh-process RED tests**

Use temporary `ENV_FILE` files and clean Python subprocesses to assert `wsgi.app`
and `manage.app` receive DB/JWT values before configuration classes are created,
and that explicit process environment values override dotenv values.

- [ ] **Step 3: Apply the minimal `config.py` bootstrap-order correction**

Load the resolved profile dotenv before class-level `os.getenv()` expressions
are evaluated, without changing the public profile API.

- [ ] **Step 4: Run backend gates and open the independent scaffolding PR**

Run Ruff, format, mypy, full pytest, and fresh-process tests. Commit with a
Conventional Commit and tag the PR `scaffolding`.
