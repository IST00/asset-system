# CLAUDE.md

> 项目级入口，给 Claude Code / Cursor / Copilot 等 AI 编码工具使用。
> 本仓是 `../scaffolding-java/` 的 Python 孪生：后端 Flask 替代 Spring Boot，前端完全复用。

## 仓库布局

`scaffolding-python/` 是单仓双 workspace：

- `back/` — Flask 3 + Python 3.13（pip + pyproject.toml）。包根 `app.*`。
- `front/` — React 18 + TypeScript + Vite 5（npm），与 Java 版一致。

根 `package.json` 是编排层：husky、commitlint、lint-staged。所有 npm/docker 命令从仓库根目录执行。

## 动手前必读

| 你要改的东西 | 约定位置 |
| --- | --- |
| `back/` 任意文件 | 本文件 §后端 + `../scaffolding-java/docs/conventions/backend.md` 的精神 |
| `front/` 任意文件 | `../scaffolding-java/docs/conventions/frontend.md`（规则完全一致） |
| 提交 / 分支 / CI | 本文件 §工作流 |

## 不可越线的 10 条

1. **Blueprint 禁止直接 import `app.models` 或 `app.extensions.db`**，走 `app.services`。
2. **Blueprint 禁止返回 model 实例**，过 marshmallow `*Schema` 或 service 出参 dict。
3. **失败抛 `BusinessException(ResultCode.X)`**，不要手写 `Result.fail(code, msg)`。
4. **Schema 变更走 Alembic**，`migrations/versions/{NNN}_*.py`；**禁止**改动已合入的迁移；**禁止**引入 Django / FastAPI / Peewee。
5. **前端所有 HTTP 走 `@/api/http`**，禁止 `import axios` / 裸 `fetch`。
6. **状态分层**：`useState`（UI）/ Zustand（全局）/ React Query（远端），不互混。
7. **路径统一 `@/` 别名**，禁止 `../../..`。
8. **ESLint 零 warning，TypeScript 禁 `any`**。
9. **后端 lint 零告警**：`ruff check .`、`ruff format --check .`、`mypy app/ config.py` 全过。
10. **Conventional Commits，禁用 `--no-verify` 绕 husky**。

## 后端分层

```
api (blueprint) → services → models (SQLAlchemy) → db session
```

- **Blueprint** 只负责 HTTP 边界：schema 校验（marshmallow load / dump）、JWT 鉴权（`jwt_required`）、调 service。
- **Service** 是业务中心：事务、查库、抛 `BusinessException`。
- **Model** 是 SQLAlchemy `db.Model` 子类；`created_at` / `updated_at` 在模型里 default + onupdate。
- **Result** / **PageResult** / **ResultCode** / **BusinessException** 都在 `app.common`；全局错误处理器把它们翻译为统一 JSON envelope。
- **JWT**：`flask_jwt_extended` 负责签发/校验；blueprint 用 `get_jwt_identity()` / `get_jwt()`，**禁止**手解 Authorization 头。
- **迁移**：`FLASK_APP=manage.py flask db upgrade` / `flask db migrate -m "..."`。文件命名 `{NNN}_<snake>.py`。

## 常用命令

从仓库根执行（部分需进入子目录）：

| 动作 | 命令 |
| --- | --- |
| 后端开发 | `cd back && python manage.py run`（或 `npm run dev:back`） |
| 后端 lint | `cd back && ruff check . && ruff format --check .` |
| 后端类型检查 | `cd back && mypy app/ config.py` |
| 后端测试 | `cd back && pytest`（单个用例：`pytest tests/test_auth.py::test_register_and_login`） |
| 迁移升级 | `cd back && FLASK_APP=manage.py flask db upgrade` |
| 新迁移 | `cd back && FLASK_APP=manage.py flask db migrate -m "add x"` |
| 前端开发 | `npm run dev:front` |
| 前端自检 | `cd front && npm run type-check && npm run lint && npm run build` |
| Docker 一键起 | `npm run docker:up` |

## Profile / 环境变量

- **dev**（默认）：SQLite `instance/dev.db`，宽松 JWT secret。
- **prod**：MySQL via `DB_URL` / `DB_HOST` / `DB_USER` / `DB_PASSWORD` / `DB_NAME`；Redis via `REDIS_HOST` / `REDIS_PORT`；`JWT_SECRET` 必须覆盖。
- **test**：内存 SQLite，pytest 自动使用。

切换：`FLASK_ENV=prod python manage.py run`。

## 给 AI 工具的操作守则

1. **先看样板再动笔**：生成 blueprint 前 `Read` 一份 `app/api/auth.py` 当模板，不要新发明分层。
2. **查证再引用**：用 `Grep` 确认类存在，不要瞎猜 import 路径。
3. **改完自检**：
   - `cd back && ruff check . && mypy app/ config.py && pytest`
   - `cd front && npm run type-check && npm run lint`
4. **保持最小改动**：不顺手 "优化" 无关代码。
5. **不要绕规则**：`# noqa` / `# type: ignore` / `--no-verify` 都是最后手段，要写清理由。

## 工作流

- Conventional Commits 由 husky `commit-msg` → commitlint 强制。
- `pre-commit` 跑 `scripts/guard-conventions.sh` + `lint-staged`。
- CI 两条独立流水线：backend（ruff + mypy + pytest）+ frontend（type-check + lint + build）。
- 分支：`main` / `develop` 只接 PR；工作分支 `feature/*` / `fix/*` / `release/*` / `hotfix/*`。

## 脚手架自身怎么改

改到以下任一 = 改脚手架本体，走独立 PR + tag `scaffolding`：

- `back/requirements.txt` / `back/pyproject.toml` 核心依赖
- `front/package.json` dependencies
- `Result` / `ResultCode` / `BusinessException` / `register_error_handlers`
- `config.py`、`app/__init__.py`、`.husky/*`、`commitlint.config.cjs`、`.eslintrc.cjs`、`tsconfig.json`
- 本 `CLAUDE.md`

---

默认开发账号：`admin` / `admin123`。
