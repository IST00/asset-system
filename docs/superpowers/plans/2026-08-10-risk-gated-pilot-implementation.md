# Risk-Gated Asset System Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and execute a reproducible eight-stage pilot gate that validates the asset system with isolated infrastructure, locked dependencies, simulated data, explicit permissions, UTC/Beijing time handling, controlled users, and auditable exit decisions.

**Architecture:** Treat the pilot as a sequence of blocking gates over one immutable candidate build. Code-level contracts enforce toolchain, MySQL, UTC serialization, and Beijing display behavior; repository checklists capture functional, permission, brand, UAT, regression, and release evidence. Each gate emits a signed Markdown record and blocks the next gate whenever a P0/P1 defect or environment mismatch exists.

**Tech Stack:** Python 3.13, Flask 3, SQLAlchemy 2, MySQL 8.4 LTS, pytest, Ruff, Mypy, Node.js 22.23.1 LTS, npm 10.9.8, React 18, TypeScript, Vite 5, Docker Compose.

---

## File map

- Create `.python-version`: declare Python 3.13 for local version managers.
- Create `.nvmrc` and `.node-version`: declare Node.js 22.23.1.
- Create `.npmrc`: enforce exact dependency saves and engine checks.
- Modify `package.json` and `front/package.json`: exact engines, npm package manager, exact direct dependency versions, gate commands.
- Create root `package-lock.json`; refresh `front/package-lock.json`: lock complete npm dependency graphs.
- Create `back/requirements.lock`: hash-locked Python direct and transitive dependencies.
- Create `back/pyproject.toml`: declare Python 3.13 project metadata.
- Modify `back/Dockerfile`: install the hash-locked dependency graph on Python 3.13.
- Create `front/Dockerfile` and `front/nginx.conf`: reproducible Node 22 build and static serving.
- Modify `docker-compose.yml`: use UTC container time and health-aware startup.
- Create `scripts/check_toolchain.py`: verify Python, Node, npm, lockfiles, and Docker declarations without changing state.
- Create `back/app/environment/database_contract.py`: validate MySQL version, charset, and UTC session metadata.
- Create `back/app/environment/__init__.py`: export database contract functions.
- Modify `back/config.py`: initialize production MySQL sessions in UTC.
- Modify `back/manage.py`: expose `flask check-database-environment`.
- Modify `back/docker-entrypoint.sh`: run the database contract before migrations.
- Create `back/app/common/datetime.py`: normalize aware/naive database values to UTC and emit ISO 8601 `Z` strings.
- Create `back/app/common/json_provider.py`: serialize all Flask datetimes as UTC.
- Create `back/app/schemas/fields.py`: timezone-aware Marshmallow datetime boundary.
- Modify `back/app/__init__.py`, `back/app/schemas/inventory.py`, and `back/app/schemas/user.py`: wire UTC serialization and timezone-aware request fields.
- Create `front/src/utils/dateTime.ts`: parse API instants as UTC and format explicitly in `Asia/Shanghai`.
- Create `front/src/utils/dateTime.test.ts`: deterministic UTC-to-Beijing tests.
- Modify frontend pages and asset formatters that call `new Date(...).toLocaleString(...)` directly.
- Create `scripts/run-quality-gate.sh`: one command for backend and frontend quality checks.
- Create `scripts/verify-clean-install.sh`: install Python/npm dependencies using empty temporary caches.
- Create `docs/testing/pilot/README.md`: gate workflow and evidence index.
- Create `docs/testing/pilot/gate-record-template.md`: versioned stage decision record.
- Create `docs/testing/pilot/defect-register.md`: P0-P3 defect tracking table.
- Create `docs/testing/pilot/functional-checklist.md`: core business test cases.
- Create `docs/testing/pilot/permission-matrix.md`: role/scope test matrix.
- Create `docs/testing/pilot/simulation-data-catalog.md`: deterministic fake data specification.
- Create `docs/testing/pilot/brand-and-usability-checklist.md`: logo, UI, accessibility, and device checks.
- Create `docs/testing/pilot/daily-runbook.md`: 3-5 day pilot operations.
- Create `docs/testing/pilot/release-readiness.md`: regression and production-preparation gate.
- Create `back/tests/test_environment_contract.py`: repository/toolchain contracts.
- Create `back/tests/test_database_contract.py`: MySQL metadata validation tests.
- Create `back/tests/test_utc_datetime.py`: UTC serialization and timezone-input tests.

## Task 1: Establish gate records and defect governance

**Files:**

- Create: `docs/testing/pilot/README.md`
- Create: `docs/testing/pilot/gate-record-template.md`
- Create: `docs/testing/pilot/defect-register.md`

- [ ] **Step 1: Create the pilot evidence index**

Create `docs/testing/pilot/README.md` with these fixed rules:

```markdown
# 小范围试运行证据索引

范围：5～10 名用户，3～5 个工作日，只使用模拟数据和独立试运行数据库。

## 执行顺序
1. 环境与安全
2. 自动化质量
3. 核心业务
4. 模拟数据与权限
5. 品牌与易用性
6. 小范围试运行
7. 缺陷回归
8. 正式上线准备

## 阻断规则
- P0：立即停止并隔离环境。
- P1：修复并完成相关全量回归后才能继续。
- P2：试运行前修复；风险接受必须写明负责人和期限。
- P3：可进入整改清单，但必须有负责人和期限。
- 每个阶段 P0/P1 为零后才能签署出口结论。

## 每次执行必须记录
- Git commit、镜像标识、Python/Node/npm/pip/MySQL 版本
- Python/npm 锁文件摘要
- 数据库库名和账号只记录标识，不记录密码
- 模拟数据快照标识、执行人、开始/结束时间
- 用例结果、缺陷编号、脱敏日志或截图位置
```

- [ ] **Step 2: Create the stage decision template**

Create `docs/testing/pilot/gate-record-template.md`:

```markdown
# 阶段门禁记录

| 字段 | 内容 |
| --- | --- |
| 阶段 | 环境与安全 / 自动化质量 / 核心业务 / 模拟数据与权限 / 品牌与易用性 / 小范围试运行 / 缺陷回归 / 正式上线准备 |
| 候选版本 | Git commit + 镜像标识 |
| 环境 | pilot |
| 模拟数据快照 | 快照标识 |
| 执行人 | 姓名或内部账号 |
| 开始时间 | ISO 8601，北京时间 |
| 结束时间 | ISO 8601，北京时间 |

## 准入检查
- [ ] 上一阶段出口已签署
- [ ] 候选版本未变化
- [ ] 环境和模拟数据快照已冻结

## 结果
| 检查项 | 通过/失败/阻断 | 证据位置 | 缺陷编号 |
| --- | --- | --- | --- |

## 缺陷统计
| P0 | P1 | P2 | P3 |
| ---: | ---: | ---: | ---: |
| 0 | 0 | 0 | 0 |

## 出口结论
- [ ] 通过，可进入下一阶段
- [ ] 阻断，修复后重新执行本阶段

业务负责人：________  系统管理员：________  技术负责人：________
```

- [ ] **Step 3: Create the defect register**

Create `docs/testing/pilot/defect-register.md` with columns:

```markdown
# 试运行缺陷登记

| 编号 | 发现阶段 | 严重级别 | 复现步骤 | 期望结果 | 实际结果 | 负责人 | 修复版本 | 回归用例 | 状态 | 截止日期 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
```

Allowed status values are `OPEN`, `FIXING`, `READY_FOR_RETEST`, `VERIFIED`, and `RISK_ACCEPTED`. `RISK_ACCEPTED` is forbidden for P0/P1.

- [ ] **Step 4: Verify the documentation has no unresolved markers**

Run:

```bash
rg -n 'TBD|TODO|待定|稍后补充' docs/testing/pilot
```

Expected: no matches.

- [ ] **Step 5: Commit gate governance**

```bash
git add docs/testing/pilot/README.md \
  docs/testing/pilot/gate-record-template.md \
  docs/testing/pilot/defect-register.md
git commit -m "docs(test): add pilot gate governance"
```

## Task 2: Lock Python, Node, pip, and npm environments

**Files:**

- Create: `.python-version`
- Create: `.nvmrc`
- Create: `.node-version`
- Create: `.npmrc`
- Create: `back/requirements.lock`
- Create: `package-lock.json`
- Modify: `package.json`
- Modify: `front/package.json`
- Modify: `front/package-lock.json`
- Create: `back/pyproject.toml`
- Test: `back/tests/test_environment_contract.py`

- [ ] **Step 1: Write the failing repository contract tests**

Create `back/tests/test_environment_contract.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _json(path: str) -> dict:
    return json.loads((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))


def test_python_and_node_versions_are_declared() -> None:
    assert (REPOSITORY_ROOT / ".python-version").read_text().strip() == "3.13"
    assert (REPOSITORY_ROOT / ".nvmrc").read_text().strip() == "22.23.1"
    assert (REPOSITORY_ROOT / ".node-version").read_text().strip() == "22.23.1"


def test_npm_runtime_is_exactly_declared() -> None:
    for filename in ("package.json", "front/package.json"):
        package = _json(filename)
        assert package["engines"]["node"] == "22.23.x"
        assert package["engines"]["npm"] == "10.9.8"
        assert package["packageManager"] == "npm@10.9.8"


def test_dependency_lockfiles_exist() -> None:
    for filename in (
        "package-lock.json",
        "front/package-lock.json",
        "back/requirements.lock",
    ):
        assert (REPOSITORY_ROOT / filename).is_file()


def test_python_lock_uses_hashes() -> None:
    lock = (REPOSITORY_ROOT / "back/requirements.lock").read_text().lower()
    assert "--hash=sha256:" in lock
    assert "flask==3.0.3" in lock


def test_direct_npm_dependencies_are_exact() -> None:
    for filename in ("package.json", "front/package.json"):
        package = _json(filename)
        dependencies = {
            **package.get("dependencies", {}),
            **package.get("devDependencies", {}),
        }
        assert dependencies
        assert all(not value.startswith(("^", "~", ">", "<")) for value in dependencies.values())
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
cd back
.venv/bin/python -m pytest tests/test_environment_contract.py -q
```

Expected: failures for missing version files, missing root npm lockfile, missing Python lockfile, non-exact npm engines, and caret dependency ranges.

- [ ] **Step 3: Declare exact runtimes**

Create these files:

```text
# .python-version
3.13

# .nvmrc and .node-version
22.23.1
```

Create `.npmrc`:

```ini
engine-strict=true
save-exact=true
package-lock=true
```

In both package files add:

```json
"engines": {
  "node": "22.23.x",
  "npm": "10.9.8"
},
"packageManager": "npm@10.9.8"
```

Remove `^` and `~` from every direct dependency version while preserving the numeric version already declared in each package file.

In `back/pyproject.toml`, set:

```toml
[project]
requires-python = "==3.13.*"
```

If `[project]` already exists, add only `requires-python`; do not duplicate the table.

- [ ] **Step 4: Generate fresh lockfiles without using project caches**

Run from the repository root:

```bash
LOCK_CACHE="$(mktemp -d)"
UV_CACHE_DIR="$LOCK_CACHE/uv" uv pip compile \
  --python-version 3.13 \
  --generate-hashes \
  --no-cache \
  --output-file back/requirements.lock \
  back/requirements.txt
npm install --package-lock-only --ignore-scripts --cache "$LOCK_CACHE/npm-root"
npm --prefix front install --package-lock-only --ignore-scripts \
  --cache "$LOCK_CACHE/npm-front"
```

Expected: all three lockfiles are generated; no `node_modules` content is copied into a lockfile.

- [ ] **Step 5: Verify GREEN**

```bash
cd back
.venv/bin/python -m pytest tests/test_environment_contract.py -q
cd ..
npm ci --ignore-scripts --cache "$(mktemp -d)"
npm --prefix front ci --ignore-scripts --cache "$(mktemp -d)"
```

Expected: environment-contract tests pass and both npm clean installs exit 0.

- [ ] **Step 6: Commit runtime and lock declarations**

```bash
git add .python-version .nvmrc .node-version .npmrc \
  package.json package-lock.json front/package.json front/package-lock.json \
  back/pyproject.toml back/requirements.lock \
  back/tests/test_environment_contract.py
git commit -m "build: lock Python and Node environments"
```

## Task 3: Make clean installation and Docker builds reproducible

**Files:**

- Modify: `back/Dockerfile`
- Create: `front/Dockerfile`
- Create: `front/nginx.conf`
- Modify: `docker-compose.yml`
- Create: `scripts/check_toolchain.py`
- Create: `scripts/verify-clean-install.sh`
- Modify: `back/tests/test_environment_contract.py`

- [ ] **Step 1: Add failing Docker/toolchain contract tests**

Append to `back/tests/test_environment_contract.py`:

```python
def test_dockerfiles_use_required_runtime_series() -> None:
    backend = (REPOSITORY_ROOT / "back/Dockerfile").read_text()
    frontend = (REPOSITORY_ROOT / "front/Dockerfile").read_text()
    assert "FROM python:3.13-slim-bookworm" in backend
    assert "requirements.lock" in backend
    assert "--require-hashes" in backend
    assert "FROM node:22.23.1-alpine" in frontend
    assert "npm ci --ignore-scripts" in frontend


def test_compose_runs_containers_in_utc() -> None:
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text()
    assert compose.count("TZ: UTC") == 2
```

- [ ] **Step 2: Run and verify RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_environment_contract.py -q
```

Expected: missing frontend Dockerfile, unlocked backend installation, and missing UTC container environment cause failures.

- [ ] **Step 3: Pin backend installation to the hash lock**

Change `back/Dockerfile` to:

```dockerfile
FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=UTC

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock .
RUN python -m pip install --no-cache-dir pip==25.2 \
    && python -m pip install --no-cache-dir --require-hashes -r requirements.lock

COPY . .
RUN chmod +x docker-entrypoint.sh

EXPOSE 8080 8081
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
```

- [ ] **Step 4: Add the frontend production image**

Create `front/Dockerfile`:

```dockerfile
FROM node:22.23.1-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build:prod

FROM nginx:1.28.0-alpine
ENV TZ=UTC
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
```

Create `front/nginx.conf`:

```nginx
server {
    listen 80;
    server_name _;

    location /api/ {
        proxy_pass http://back:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Request-ID $http_x_request_id;
    }

    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 5: Set UTC in Compose**

Under both `back.environment` and `front.environment` in `docker-compose.yml`, add:

```yaml
TZ: UTC
```

- [ ] **Step 6: Add a read-only toolchain checker**

Create `scripts/check_toolchain.py`. It uses the running Python interpreter plus `node --version` and `npm --version`, compares them with `3.13.x`, `22.23.1`, and `10.9.8`, verifies the three lockfiles exist, prints only version results, and exits 1 on any mismatch. Keep the checker independent of Flask and database configuration:

```python
#!/usr/bin/env python3
from __future__ import annotations

import platform
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _command_version(command: str) -> str:
    completed = subprocess.run(
        [command, "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return "unavailable"
    return completed.stdout.strip().removeprefix("v")


def main() -> int:
    python = ".".join(platform.python_version_tuple()[:2])
    node = _command_version("node")
    npm = _command_version("npm")
    lockfiles = (
        ROOT / "package-lock.json",
        ROOT / "front/package-lock.json",
        ROOT / "back/requirements.lock",
    )
    results = (
        ("python", python, python == "3.13"),
        ("node", node, node == "22.23.1"),
        ("npm", npm, npm == "10.9.8"),
    )
    for name, version, valid in results:
        print(f"{name}={version} status={'ok' if valid else 'mismatch'}")
    found = sum(path.is_file() for path in lockfiles)
    print(f"lockfiles={found}/3 status={'ok' if found == 3 else 'mismatch'}")
    return 0 if all(valid for _, _, valid in results) and found == 3 else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

On a compliant machine the output is:

```text
python=3.13 status=ok
node=22.23.1 status=ok
npm=10.9.8 status=ok
lockfiles=3/3 status=ok
```

- [ ] **Step 7: Add a no-cache clean-install script**

Create `scripts/verify-clean-install.sh`. It creates one temporary workspace, builds a new Python 3.13 venv, synchronizes the hash lock without cache, performs both npm installs in copied workspaces with isolated caches, runs frontend verification, removes the workspace through a trap, and never reads deployment dotenv files:

```bash
#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temporary_root="$(mktemp -d)"
trap 'rm -rf "$temporary_root"' EXIT

uv venv --python 3.13 "$temporary_root/python"
UV_CACHE_DIR="$temporary_root/uv-cache" uv pip sync \
  --python "$temporary_root/python/bin/python" \
  --no-cache \
  "$repository_root/back/requirements.lock"

mkdir -p "$temporary_root/root"
cp "$repository_root/package.json" "$repository_root/package-lock.json" \
  "$temporary_root/root/"
npm --prefix "$temporary_root/root" ci --ignore-scripts \
  --cache "$temporary_root/npm-root-cache"

rsync -a \
  --exclude node_modules \
  --exclude dist \
  "$repository_root/front/" "$temporary_root/front/"
npm --prefix "$temporary_root/front" ci --ignore-scripts \
  --cache "$temporary_root/npm-front-cache"
npm --prefix "$temporary_root/front" run type-check
npm --prefix "$temporary_root/front" test
npm --prefix "$temporary_root/front" run lint
npm --prefix "$temporary_root/front" run build:prod
```

- [ ] **Step 8: Verify GREEN and build images**

```bash
cd back
.venv/bin/python -m pytest tests/test_environment_contract.py -q
cd ..
python3.13 scripts/check_toolchain.py
scripts/verify-clean-install.sh
docker compose build --no-cache back front
```

Expected: contracts pass, clean installation exits 0, and both images build without reusing local dependency directories.

- [ ] **Step 9: Commit reproducible builds**

```bash
git add back/Dockerfile front/Dockerfile front/nginx.conf docker-compose.yml \
  scripts/check_toolchain.py scripts/verify-clean-install.sh \
  back/tests/test_environment_contract.py
git commit -m "build: make pilot environments reproducible"
```

## Task 4: Enforce MySQL 8.4, utf8mb4, and UTC sessions

**Files:**

- Create: `back/app/environment/__init__.py`
- Create: `back/app/environment/database_contract.py`
- Create: `back/tests/test_database_contract.py`
- Modify: `back/config.py`
- Modify: `back/manage.py`
- Modify: `back/docker-entrypoint.sh`
- Modify: `back/.env.pilot.example`
- Modify: `back/.env.deploy.example`

- [ ] **Step 1: Write failing database metadata tests**

Create `back/tests/test_database_contract.py`:

```python
from __future__ import annotations

import pytest

from app.environment.database_contract import validate_database_contract


def _metadata(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "version": "8.4.3",
        "character_set_server": "utf8mb4",
        "character_set_database": "utf8mb4",
        "character_set_connection": "utf8mb4",
        "session_time_zone": "+00:00",
        "utc_offset_seconds": 0,
    }
    values.update(overrides)
    return values


def test_mysql_84_utf8mb4_utc_is_accepted() -> None:
    validate_database_contract(_metadata(), required_series="8.4")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"version": "8.0.42"}, "version"),
        ({"character_set_database": "utf8mb3"}, "charset"),
        ({"character_set_connection": "latin1"}, "charset"),
        ({"session_time_zone": "+08:00"}, "time zone"),
        ({"utc_offset_seconds": 28800}, "UTC offset"),
    ],
)
def test_database_contract_rejects_mismatches(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(RuntimeError, match=message):
        validate_database_contract(_metadata(**overrides), required_series="8.4")
```

- [ ] **Step 2: Run and verify RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_database_contract.py -q
```

Expected: collection fails because `app.environment.database_contract` does not exist.

- [ ] **Step 3: Implement the pure database contract**

Create `back/app/environment/database_contract.py` with:

```python
from __future__ import annotations

from collections.abc import Mapping


def validate_database_contract(
    metadata: Mapping[str, object], *, required_series: str
) -> None:
    failures: list[str] = []
    version = str(metadata.get("version") or "")
    if not version.startswith(required_series + "."):
        failures.append(f"version must be MySQL {required_series}")

    charset_keys = (
        "character_set_server",
        "character_set_database",
        "character_set_connection",
    )
    if any(str(metadata.get(key) or "").lower() != "utf8mb4" for key in charset_keys):
        failures.append("charset must be utf8mb4")

    if str(metadata.get("session_time_zone") or "") not in {"+00:00", "UTC"}:
        failures.append("time zone must be UTC")
    if abs(int(metadata.get("utc_offset_seconds") or 0)) > 1:
        failures.append("UTC offset must be zero")

    if failures:
        raise RuntimeError("Database environment mismatch: " + "; ".join(failures))
```

Export `validate_database_contract` from `back/app/environment/__init__.py`.

- [ ] **Step 4: Make production connections initialize in UTC**

In `ProdConfig` in `back/config.py`, override:

```python
SQLALCHEMY_ENGINE_OPTIONS: dict = {
    **BaseConfig.SQLALCHEMY_ENGINE_OPTIONS,
    "connect_args": {"init_command": "SET time_zone = '+00:00'"},
}
MYSQL_REQUIRED_SERIES: str = os.getenv("MYSQL_REQUIRED_SERIES", "8.4")
```

Add `MYSQL_REQUIRED_SERIES=8.4` to both pilot and deployment example env files.

- [ ] **Step 5: Add the Flask database preflight command**

Add `check-database-environment` to `back/manage.py`. Within an application context, execute one SQL statement through `db.session.execute(text(...)).mappings().one()`:

```sql
SELECT VERSION() AS version,
       @@character_set_server AS character_set_server,
       @@character_set_database AS character_set_database,
       @@character_set_connection AS character_set_connection,
       @@session.time_zone AS session_time_zone,
       TIMESTAMPDIFF(SECOND, UTC_TIMESTAMP(), NOW()) AS utc_offset_seconds
```

Pass the mapping to `validate_database_contract`. Print only:

```text
database environment contract passed
```

Do not print the DB URI, host, username, database name, or query result values.

- [ ] **Step 6: Block container migration on a bad database contract**

In `back/docker-entrypoint.sh`, before `flask db upgrade`, add:

```sh
echo "Checking database environment contract..."
FLASK_APP=manage.py flask check-database-environment
```

- [ ] **Step 7: Verify GREEN**

```bash
cd back
.venv/bin/python -m pytest tests/test_database_contract.py tests/test_runtime_security.py -q
FLASK_ENV=prod ENV_FILE="$PWD/.env.pilot" \
  .venv/bin/flask --app manage.py check-database-environment
```

Expected: unit tests pass. The real pilot command exits 0 only when MySQL is 8.4.x, all three charsets are `utf8mb4`, and the session offset is zero.

- [ ] **Step 8: Commit the database gate**

```bash
git add back/app/environment back/tests/test_database_contract.py back/config.py \
  back/manage.py back/docker-entrypoint.sh \
  back/.env.pilot.example back/.env.deploy.example
git commit -m "feat(environment): enforce MySQL pilot contract"
```

## Task 5: Guarantee UTC storage and API serialization

**Files:**

- Create: `back/app/common/datetime.py`
- Create: `back/app/common/json_provider.py`
- Create: `back/app/schemas/fields.py`
- Create: `back/tests/test_utc_datetime.py`
- Modify: `back/app/__init__.py`
- Modify: `back/app/schemas/inventory.py`
- Modify: `back/app/schemas/user.py`

- [ ] **Step 1: Write failing UTC boundary tests**

Create `back/tests/test_utc_datetime.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from marshmallow import ValidationError

from app import create_app
from app.common.datetime import isoformat_utc, normalize_utc
from app.schemas.fields import UTCDateTime
from config import TestConfig


def test_naive_database_datetime_is_interpreted_as_utc() -> None:
    value = normalize_utc(datetime(2026, 8, 10, 0, 0, 0))
    assert value.tzinfo == timezone.utc
    assert isoformat_utc(value) == "2026-08-10T00:00:00Z"


def test_offset_datetime_is_converted_to_utc() -> None:
    china = timezone(timedelta(hours=8))
    value = datetime(2026, 8, 10, 8, 0, 0, tzinfo=china)
    assert isoformat_utc(value) == "2026-08-10T00:00:00Z"


def test_request_datetime_requires_an_offset() -> None:
    field = UTCDateTime()
    with pytest.raises(ValidationError, match="时区"):
        field.deserialize("2026-08-10T08:00:00")
    assert field.deserialize("2026-08-10T08:00:00+08:00").tzinfo == timezone.utc


def test_flask_json_provider_emits_utc_z() -> None:
    app = create_app(TestConfig)
    with app.app_context():
        encoded = app.json.dumps({"created_at": datetime(2026, 8, 10, 0, 0, 0)})
    assert '"created_at": "2026-08-10T00:00:00Z"' in encoded
```

- [ ] **Step 2: Run and verify RED**

```bash
cd back
.venv/bin/python -m pytest tests/test_utc_datetime.py -q
```

Expected: collection fails because UTC helpers and `UTCDateTime` do not exist.

- [ ] **Step 3: Implement UTC normalization**

Create `back/app/common/datetime.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone


def normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def isoformat_utc(value: datetime) -> str:
    return normalize_utc(value).isoformat().replace("+00:00", "Z")
```

- [ ] **Step 4: Implement global Flask UTC JSON output**

Create `back/app/common/json_provider.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from flask.json.provider import DefaultJSONProvider

from app.common.datetime import isoformat_utc


class UTCJSONProvider(DefaultJSONProvider):
    @staticmethod
    def default(value: Any) -> Any:
        if isinstance(value, datetime):
            return isoformat_utc(value)
        return DefaultJSONProvider.default(value)
```

In `create_app`, set `app.json_provider_class = UTCJSONProvider` and recreate `app.json` immediately after constructing the Flask instance.

- [ ] **Step 5: Implement the Marshmallow timezone boundary**

Create `back/app/schemas/fields.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from marshmallow import ValidationError, fields

from app.common.datetime import isoformat_utc, normalize_utc


class UTCDateTime(fields.DateTime):
    def _deserialize(self, value: Any, attr: str | None, data: Any, **kwargs: Any) -> datetime:
        parsed = super()._deserialize(value, attr, data, **kwargs)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValidationError("时间必须包含时区偏移")
        return normalize_utc(parsed)

    def _serialize(self, value: Any, attr: str | None, obj: Any, **kwargs: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise ValidationError("时间值格式无效")
        return isoformat_utc(value)
```

Replace request deadline fields in `inventory.py` and all response datetime fields in `user.py` with `UTCDateTime`.

- [ ] **Step 6: Verify GREEN and regress API serialization**

```bash
cd back
.venv/bin/python -m pytest tests/test_utc_datetime.py \
  tests/test_inventory_api.py tests/test_auth.py tests/test_account_security.py -q
```

Expected: all selected tests pass; API datetimes contain `Z`; naive incoming request datetimes are rejected.

- [ ] **Step 7: Commit UTC backend boundaries**

```bash
git add back/app/common/datetime.py back/app/common/json_provider.py \
  back/app/schemas/fields.py back/app/__init__.py \
  back/app/schemas/inventory.py back/app/schemas/user.py \
  back/tests/test_utc_datetime.py
git commit -m "fix(time): normalize backend datetimes to UTC"
```

## Task 6: Display every instant in Beijing time

**Files:**

- Create: `front/src/utils/dateTime.ts`
- Create: `front/src/utils/dateTime.test.ts`
- Modify: `front/src/features/operations/AuditLogs.tsx`
- Modify: `front/src/features/operations/Imports.tsx`
- Modify: `front/src/features/operations/Profile.tsx`
- Modify: `front/src/features/operations/Notifications.tsx`
- Modify: `front/src/features/operations/Settings.tsx`
- Modify: `front/src/features/assets/detail/detailFormatters.ts`
- Modify: `front/src/features/assets/detail/detailFormatters.test.ts`

- [ ] **Step 1: Write failing timezone-independent frontend tests**

Create `front/src/utils/dateTime.test.ts`:

```typescript
import assert from 'node:assert/strict'
import test from 'node:test'
import { beijingDateKey, formatBeijingDateTime, parseUtcInstant } from './dateTime.ts'

test('formats UTC instant as Beijing time', () => {
  assert.equal(formatBeijingDateTime('2026-08-10T00:00:00Z'), '2026-08-10 08:00:00')
})

test('treats legacy naive API datetime as UTC', () => {
  assert.equal(parseUtcInstant('2026-08-10T00:00:00').toISOString(), '2026-08-10T00:00:00.000Z')
})

test('computes calendar date in Asia Shanghai', () => {
  assert.equal(beijingDateKey('2026-08-09T16:30:00Z'), '2026-08-10')
})
```

- [ ] **Step 2: Run and verify RED**

```bash
cd front
npm test -- src/utils/dateTime.test.ts
```

Expected: test module fails to import because `dateTime.ts` does not exist.

- [ ] **Step 3: Implement the centralized formatter**

Create `front/src/utils/dateTime.ts`:

```typescript
const API_OFFSET = /(Z|[+-]\d{2}:\d{2})$/i

export function parseUtcInstant(value: string): Date {
  const normalized = API_OFFSET.test(value) ? value : `${value}Z`
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) throw new Error('Invalid API datetime')
  return date
}

function parts(value: string): Record<string, string> {
  const formatter = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hourCycle: 'h23',
  })
  return Object.fromEntries(
    formatter.formatToParts(parseUtcInstant(value)).map((part) => [part.type, part.value]),
  )
}

export function formatBeijingDateTime(value: string): string {
  const p = parts(value)
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}:${p.second}`
}

export function beijingDateKey(value: string): string {
  return formatBeijingDateTime(value).slice(0, 10)
}
```

- [ ] **Step 4: Replace browser-local formatting**

Import `formatBeijingDateTime` wherever API instants are displayed. Replace every `new Date(apiValue).toLocaleString('zh-CN')` and local `Intl.DateTimeFormat` helper with the central function. Replace audit-log “today” comparisons with `beijingDateKey`.

Keep date-only asset fields such as `purchase_date` unchanged; they represent calendar dates, not instants.

- [ ] **Step 5: Verify GREEN and scan for remaining local-time formatting**

```bash
cd front
npm test
npm run type-check
npm run lint
rg -n "new Date\([^)]*(created_at|updated_at|deadline_at|server_time|last_seen_at)[^)]*\)\.toLocaleString" src
```

Expected: tests, type-check, and lint pass; the final `rg` returns no matches.

- [ ] **Step 6: Commit Beijing-time rendering**

```bash
git add front/src/utils/dateTime.ts front/src/utils/dateTime.test.ts \
  front/src/features/operations/AuditLogs.tsx \
  front/src/features/operations/Imports.tsx \
  front/src/features/operations/Profile.tsx \
  front/src/features/operations/Notifications.tsx \
  front/src/features/operations/Settings.tsx \
  front/src/features/assets/detail/detailFormatters.ts \
  front/src/features/assets/detail/detailFormatters.test.ts
git commit -m "fix(front): render API instants in Beijing time"
```

## Task 7: Add the executable functional, permission, and simulation checklists

**Files:**

- Create: `docs/testing/pilot/functional-checklist.md`
- Create: `docs/testing/pilot/permission-matrix.md`
- Create: `docs/testing/pilot/simulation-data-catalog.md`

- [ ] **Step 1: Create the functional checklist**

Create `functional-checklist.md` with one checkbox per test ID and columns for result, evidence, and defect. Include at least these exact cases:

```text
AUTH-01 login success; AUTH-02 wrong password; AUTH-03 lock threshold;
AUTH-04 forced password change; AUTH-05 logout/revocation; AUTH-06 expired JWT;
RBAC-01 role creation; RBAC-02 permission assignment; RBAC-03 cross-org denial;
MASTER-01 organization CRUD; MASTER-02 location CRUD; MASTER-03 category CRUD;
MASTER-04 supplier CRUD; MASTER-05 referenced-record deletion denial;
STOCK-01 create stock-in; STOCK-02 approve; STOCK-03 reject/resubmit;
STOCK-04 asset code uniqueness; STOCK-05 duplicate submission;
ASSET-01 list/filter/page; ASSET-02 update; ASSET-03 batch update;
ASSET-04 transfer; ASSET-05 repair/complete; ASSET-06 scrap;
USE-01 personal use; USE-02 public use; USE-03 approval execution;
RETURN-01 personal return; RETURN-02 public return; RETURN-03 manager confirmation;
INV-01 create/publish; INV-02 real scan; INV-03 found result;
INV-04 loss result; INV-05 exception resolution; INV-06 end/reopen;
APPROVAL-01 publish flow; APPROVAL-02 approve; APPROVAL-03 reject;
APPROVAL-04 withdraw; APPROVAL-05 retry failed execution;
IMPORT-01 template download; IMPORT-02 valid preview; IMPORT-03 invalid preview;
IMPORT-04 confirm; IMPORT-05 duplicate idempotency;
EXPORT-01 CSV; EXPORT-02 PDF label; EXPORT-03 authorization; EXPORT-04 expiry cleanup;
ATTACH-01 upload; ATTACH-02 type/size rejection; ATTACH-03 cover;
ATTACH-04 authorized download; ATTACH-05 cross-scope denial; ATTACH-06 void;
OPS-01 audit event; OPS-02 security event; OPS-03 system status;
OPS-04 liveness; OPS-05 readiness database failure.
```

For every case include normal, invalid-input, repeat-submit, concurrent-update, permission-denied, and missing-record variants when applicable.

- [ ] **Step 2: Create the permission matrix**

Create `permission-matrix.md` for these actors:

```text
SUPER_ADMIN, ASSET_ADMIN_ORG_A, INVENTORY_ADMIN_ORG_A,
APPROVER_ORG_A, USER_ORG_A, USER_ORG_B, DISABLED_USER
```

Test view/create/update/approve/export/download/audit capabilities across Org A and Org B. Every unauthorized combination must expect HTTP 401/403 or the project’s unified forbidden result, and must confirm no database mutation or audit omission.

- [ ] **Step 3: Create the simulation data catalog**

Create `simulation-data-catalog.md` with deterministic codes that cannot be confused with production:

```text
Organizations: SIM-ORG-A, SIM-ORG-B, SIM-ORG-C
Departments: SIM-DEPT-A01, SIM-DEPT-A02, SIM-DEPT-B01, SIM-DEPT-B02, SIM-DEPT-C01
Locations: SIM-LOC-001 through SIM-LOC-010
Categories: SIM-CAT-IT, SIM-CAT-OFFICE, SIM-CAT-VEHICLE, SIM-CAT-TOOL, SIM-CAT-OTHER
Suppliers: SIM-SUP-001 through SIM-SUP-005
Assets: SIM-ASSET-0001 through SIM-ASSET-0200
Users: sim_super_admin, sim_asset_admin_a, sim_inventory_admin_a,
       sim_approver_a, sim_user_a, sim_user_b, sim_disabled
```

Specify 80 IDLE, 60 IN_USE, 30 REPAIRING, and 30 SCRAPPED assets. Use generated solid-color PNGs and plain-text PDFs containing `SIMULATION ONLY`; do not copy real attachments. Record the database snapshot identifier after loading.

- [ ] **Step 4: Validate checklist coverage**

```bash
for prefix in AUTH RBAC MASTER STOCK ASSET USE RETURN INV APPROVAL IMPORT EXPORT ATTACH OPS; do
  rg -q "$prefix-" docs/testing/pilot/functional-checklist.md
done
rg -q 'USER_ORG_B' docs/testing/pilot/permission-matrix.md
rg -q 'SIMULATION ONLY' docs/testing/pilot/simulation-data-catalog.md
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit test catalogs**

```bash
git add docs/testing/pilot/functional-checklist.md \
  docs/testing/pilot/permission-matrix.md \
  docs/testing/pilot/simulation-data-catalog.md
git commit -m "docs(test): add pilot functional and permission matrix"
```

## Task 8: Complete company branding and usability gate

**External prerequisite:** The brand owner supplies approved SVG files named `company-logo-horizontal.svg`, `company-logo-square.svg`, `company-logo-on-dark.svg`, and `company-logo-on-light.svg`. Do not generate or trace a company logo from screenshots.

**Files:**

- Create: `docs/testing/pilot/brand-and-usability-checklist.md`
- Add after asset approval: `front/public/brand/company-logo-horizontal.svg`
- Add after asset approval: `front/public/brand/company-logo-square.svg`
- Add after asset approval: `front/public/brand/company-logo-on-dark.svg`
- Add after asset approval: `front/public/brand/company-logo-on-light.svg`
- Modify after asset approval: `front/index.html`
- Modify after asset approval: login and shell components found by `rg -l 'logo|favicon|Scaffold' front/src front/index.html`

- [ ] **Step 1: Create the brand/usability checklist**

The checklist must cover:

```text
BRAND-01 browser favicon; BRAND-02 login logo; BRAND-03 sidebar/header logo;
BRAND-04 system/company name; BRAND-05 dark background; BRAND-06 light background;
BRAND-07 print/export branding; BRAND-08 no Scaffold text or default icon;
UI-01 loading; UI-02 empty; UI-03 API error; UI-04 forbidden;
UI-05 404; UI-06 expired session; UI-07 long Chinese text;
UI-08 1366x768; UI-09 1920x1080; UI-10 keyboard focus;
UI-11 contrast; UI-12 Beijing time; UI-13 CNY amount.
```

- [ ] **Step 2: Verify supplied assets before copying**

For each SVG, verify it has a `viewBox`, contains no scripts or external URLs, and renders against its intended background. Reject raster images embedded as base64 inside SVG.

- [ ] **Step 3: Replace branding in one central configuration**

Search first:

```bash
rg -n 'Scaffold|scaffold|logo|favicon' front/src front/index.html
```

Replace every active scaffold reference with the approved system name and approved asset path. Preserve accessibility labels such as `alt="公司 Logo"`.

- [ ] **Step 4: Verify branding and frontend gates**

```bash
rg -n 'Scaffold|scaffold' front/src front/index.html
cd front
npm test
npm run type-check
npm run lint
npm run build:prod
```

Expected: no active scaffold brand matches; all frontend commands exit 0. Complete the checklist at both required resolutions.

- [ ] **Step 5: Commit approved branding**

```bash
git add docs/testing/pilot/brand-and-usability-checklist.md \
  front/public/brand front/index.html front/src
git commit -m "feat(front): apply approved company branding"
```

## Task 9: Operate the 3-5 day pilot and regression gate

**Files:**

- Create: `docs/testing/pilot/daily-runbook.md`
- Create: `docs/testing/pilot/release-readiness.md`
- Create: `scripts/run-quality-gate.sh`
- Modify: `package.json`

- [ ] **Step 1: Create the quality gate script**

Create `scripts/run-quality-gate.sh` with `set -euo pipefail` and these commands in order:

```bash
cd back
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app/ config.py
.venv/bin/python -m pytest
cd ../front
npm run type-check
npm run lint
npm test
npm run build:prod
```

Add root package command:

```json
"quality:gate": "scripts/run-quality-gate.sh"
```

- [ ] **Step 2: Create the daily pilot runbook**

For each of 3-5 days require opening and closing checks. Opening checks: liveness, readiness, database contract, disk, latest backup, candidate commit, image identifier, active pilot users. Closing checks: login count, completed core flows, HTTP 5xx count, slow request count, DB connection failures, attachment bytes, export files, P0-P3 counts, user feedback, and next-day decision.

State explicit stop conditions: any P0, any unexplained data mismatch, connection to production, failed backup, cross-org access, or environment version drift.

- [ ] **Step 3: Create release-readiness checklist**

Include these blocking sections:

```text
final immutable image; migration and rollback; backup and restore evidence;
monitoring and alerts; certificate expiry; disk capacity; secret rotation;
least privilege; admin handover; deployment/failure/user manuals;
launch window; freeze time; acceptance owners; rollback owner;
day-one and week-one inspection schedule.
```

- [ ] **Step 4: Dry-run the automated gate**

```bash
npm run quality:gate
```

Expected: every backend and frontend command exits 0; the run stops at the first failure.

- [ ] **Step 5: Commit pilot operations artifacts**

```bash
git add scripts/run-quality-gate.sh package.json \
  docs/testing/pilot/daily-runbook.md \
  docs/testing/pilot/release-readiness.md
git commit -m "docs(test): add pilot operations and release gates"
```

## Task 10: Execute the full gate on a fresh candidate

**Files:** No new production files.

- [ ] **Step 1: Freeze the candidate**

Record `git rev-parse HEAD`, `git status --short`, image identifiers, lockfile SHA-256 values, and the simulation snapshot identifier in a copy of `gate-record-template.md`. The worktree must contain no unreviewed files.

- [ ] **Step 2: Verify toolchain and clean installation**

```bash
python3.13 scripts/check_toolchain.py
scripts/verify-clean-install.sh
docker compose build --no-cache back front
```

Expected: all commands exit 0 on Python 3.13, Node 22.23.1, npm 10.9.8.

- [ ] **Step 3: Verify environment isolation and MySQL**

```bash
back/.venv/bin/python scripts/check_environment_isolation.py \
  back/.env.pilot back/.env.deploy
cd back
FLASK_ENV=prod ENV_FILE="$PWD/.env.pilot" \
  .venv/bin/flask --app manage.py check-database-environment
```

Expected: distinct pilot/production identities; MySQL 8.4.x; `utf8mb4`; zero UTC offset; no secret values printed.

- [ ] **Step 4: Test migrations and restore**

Run all migrations against an empty pilot database, rerun upgrade to prove idempotent head state, restore the pre-test snapshot to a separate restore database, and compare migration head plus row counts for organizations, users, assets, operations, attachments, and audit records.

Expected: both databases reach the same Alembic head; recorded table counts match the snapshot manifest.

- [ ] **Step 5: Run the complete automated gate**

```bash
npm run quality:gate
```

Expected: Ruff and Mypy clean; all backend tests pass; frontend type-check, lint, tests, and production build pass.

- [ ] **Step 6: Execute functional and permission checklists**

Run every `functional-checklist.md` case and every applicable cell in `permission-matrix.md`. Attach sanitized evidence and defect numbers. Any P0/P1 blocks execution.

- [ ] **Step 7: Execute branding and usability checklist**

Verify approved assets, scaffold-removal scan, both required resolutions, error/empty/loading states, keyboard focus, Beijing time, and CNY formatting.

- [ ] **Step 8: Run controlled pilot days**

Execute `daily-runbook.md` for 3-5 workdays. Require two consecutive days with no P0/P1 and successful high-frequency flows before closing the pilot gate.

- [ ] **Step 9: Run final regression after the last fix**

Rebuild the immutable image from clean locks, repeat environment/database gates, repeat `npm run quality:gate`, and rerun every checklist case linked to a fixed defect plus its upstream/downstream flows.

- [ ] **Step 10: Sign the final decision**

Business owner, system administrator, and technical owner sign the final gate record. “Ready for production planning” is allowed only when P0/P1 are zero, every P2 is fixed or formally accepted, backup restore evidence exists, and no production data or identity was used during the pilot.
