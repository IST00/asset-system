# Workflow Conventions

> 适用范围：整个 `scaffolding-python/`
> 受众：人类开发者 + LLM 代码生成工具

---

## 1. Git 提交（Conventional Commits）

格式：

```
<type>(<scope>): <subject>
```

| type | 用途 |
| --- | --- |
| `feat` | 新功能 |
| `fix` | 修 bug |
| `docs` | 只改文档 |
| `style` | 不影响语义的格式调整 |
| `refactor` | 重构（无行为变化） |
| `perf` | 性能优化 |
| `test` | 测试 |
| `build` | 构建 / 依赖 |
| `ci` | CI 配置 |
| `chore` | 杂项 |
| `revert` | 回滚 |

### ✅

```
feat(auth): 支持 refresh token
fix(front): 修复登录后跳转空白页
refactor(back/user): 拆出 user_query_service
chore(deps): bump flask to 3.0.3
```

### ❌

```
update                              # 没 type
feat:支持refresh                    # 冒号后缺空格
增加登录                            # 没 type，全中文
```

校验由 `.husky/commit-msg` → `commitlint`（`commitlint.config.cjs` 基于 `@commitlint/config-conventional`）完成。**禁止** 用 `git commit --no-verify` 绕过；hook 挂了就是**真问题**，去修根因。

---

## 2. 分支策略

| 分支 | 用途 | 合并方式 |
| --- | --- | --- |
| `main` | 生产 | **只** 接 PR，禁直推、禁 force push |
| `develop` | 集成 | PR / FF merge |
| `feature/<id>-<desc>` | 新功能 | PR → `develop` |
| `fix/<id>-<desc>` | 缺陷 | PR → `develop` |
| `hotfix/<desc>` | 线上紧急 | PR → `main`，再 cherry-pick 回 `develop` |
| `release/<version>` | 预发 | merge `develop`，发完并回 `main` |

---

## 3. 本地钩子

| 文件 | 跑什么 |
| --- | --- |
| `.husky/pre-commit` | ① `scripts/guard-conventions.sh`（约定守护）② `lint-staged`（前端 ESLint + Prettier，见根 `package.json`） |
| `.husky/commit-msg` | `commitlint --edit $1` |

**首次 clone** 后在仓库根跑一次：

```bash
npm install            # 装 husky / commitlint / lint-staged
npm run prepare        # = husky install，把 hook 链接进 .git/hooks
```

### `scripts/guard-conventions.sh` 会拦什么

（权威文件：`scripts/guard-conventions.sh`；下面是摘要）

- `back/app/api/**.py`：
  - `from app.models ...` 或 `from app.extensions import db` —— blueprint 不许跨层摸 model / db session。
  - 手写 `Result.fail(...)` —— 应抛 `BusinessException`。
  - `jwt.decode` / `PyJWT` / `jose.jwt` —— blueprint 只能用 `flask_jwt_extended`。
- `back/app/services/**.py`：
  - 手写 `Result.fail(...)` —— 同上。
  - `jwt.decode` / `PyJWT` / `jose.jwt` —— 只允许在 `app/security/*` 里。
- `back/requirements.txt`：
  - `django` / `fastapi` / `tornado` / `peewee` —— 禁止引入竞品框架 / ORM。
- `back/migrations/versions/*.py`：
  - 文件名必须匹配 `^[0-9]{3,}_[a-z0-9_]+\.py$`。
- `front/src/**/*.{ts,tsx}`（除 `front/src/api/http.ts`）：
  - `import ... from 'axios'` —— 必须走 `@/api/http`。
  - `fetch('/api/...')` 或 `fetch('http(s)://.../:8080...')` —— 同上。
  - `from '../../...'` 起的多层相对爬楼 —— 用 `@/` 别名。
  - `: any` 显式注解（非 `.d.ts`） —— 禁 `any`。
  - 文件首 `/* eslint-disable */` —— 整文件禁用不允许。

**触发后 exit 1，commit 被终止。改到合规 → `git add` → 重新 commit。**

---

## 4. Push 前自查清单

Push 前本地至少跑过一遍：

### 后端

```bash
cd back
ruff check .
ruff format --check .
mypy app/ config.py
pytest
```

改了迁移的：

```bash
cd back
FLASK_APP=manage.py flask db upgrade      # 本地 sqlite 应用一次，确认不炸
```

### 前端

```bash
cd front
npm run type-check
npm run lint
npm run build
```

### 中间件 / 配置变更

- 改了 `app/extensions.py`、`app/__init__.py`、`config.py`、`back/.env.*`：
  - `cd back && python manage.py run` 本地起一次，看启动日志有无报错。
  - `curl http://localhost:8081/health/readiness` 看条件性 check 注册是否符合预期。

---

## 5. CI（GitHub Actions）

`.github/workflows/ci.yml` 跑两条独立 job，push / PR 到 `main` / `develop` 都触发：

- **backend**（Python 3.13）：`ruff check . → ruff format --check . → mypy → pytest`
- **frontend**（Node 20）：`npm ci → type-check → lint → build`

两条都必须绿才能 merge。

- CI 红了 → 先看日志复现根因，**不要** 盲目 rerun。
- **禁止** 加 `if: always()`、`continue-on-error: true` 把红变绿 —— 这是作弊，改规则而不是改 CI 门槛。

---

## 6. 改脚手架自身的流程

改到下列任一 = 改脚手架本体，需要**独立 PR + 打 `scaffolding` 标签 + 团队评审**：

- `back/requirements.txt` 的核心依赖（Flask / SQLAlchemy / flask-jwt-extended / marshmallow / flask-smorest / alembic / celery 的主版本）
- `front/package.json` 的 `dependencies`（`devDependencies` 除外）
- `app/common/result.py`、`app/common/errors.py`、`register_error_handlers`
- `app/__init__.py:create_app()` 的装配顺序
- `app/extensions.py` 共享实例清单
- `app/observability/**`、`app/health/**`
- `config.py`、`back/.env.dev`、`back/.env.prod`、`back/gunicorn.conf.py`、`back/wsgi.py`
- `.husky/*`、`commitlint.config.cjs`、`package.json` 的 `lint-staged`
- `front/.eslintrc.cjs`、`front/tsconfig.json`、`front/vite.config.ts`（特别是 `@/` 别名）
- 项目根 `CLAUDE.md`、`README.md`、`docs/conventions/**`
- `scripts/guard-conventions.sh`、`scripts/back-start.sh`

**普通 feature / fix PR 不要顺手带这些改动**；混进去会被驳回。

---

## 7. 给 AI 编码工具的操作守则

1. **读模板再动笔**：生成 blueprint 前 `Read` 一份 `app/api/auth.py`；生成 service 前 `Read` 一份 `app/services/auth_service.py`；前端页面同理。**不要**凭想象发明分层或导入路径。
2. **查证再引用**：`Grep` 一下类名 / 函数名确认存在，`Grep` 一下 import 路径确认对。
3. **改完自检**：按 §4 的命令跑一遍；能跑在本地的就不要假设 "应该能过"。
4. **保持 diff 最小**：不顺手重构未改动的文件；不批量 reformat；不"顺便升个依赖"。
5. **不要绕规则**：`# noqa` / `# type: ignore` / `// eslint-disable-next-line` / `--no-verify` 都是**最后手段**。必须用时在同一行写清**为什么**。
6. **提 commit 前确认 subject 是英文关键字 + 中文或英文描述**，带 type 和 scope。

---

## 8. 常见"hook 拦我"怎么办

| 报错 | 原因 | 怎么修 |
| --- | --- | --- |
| `api blueprint imports a model directly` | blueprint 里 `from app.models import ...` | 把逻辑搬到 service，blueprint 调 service |
| `do not build Result.fail() by hand` | 某处写了 `Result.fail(...)` | 改成 `raise BusinessException(result_code=ResultCode.X)` |
| `parse JWT only inside app/security/*` | 业务代码 `jwt.decode` / `PyJWT` | 用 `flask_jwt_extended.get_jwt_identity()` / `get_jwt()` |
| `migration filename must match {NNN}_<snake_desc>.py` | Alembic 生成的文件被改名 / 不合格式 | 用数字前缀 + 蛇形描述，例如 `004_add_user_email.py` |
| `do not import 'axios' directly` | 前端某文件 `import axios from 'axios'` | 改成 `import http from '@/api/http'` |
| `TypeScript 'any' is forbidden` | 显式 `: any` | 换成具体类型 / `unknown` + 类型守卫 / `Record<string, unknown>` |
| `use '@/' alias instead of '../../...'` | 多层相对 import | 换成 `@/components/Foo` 这类别名写法 |
| `stick to Flask + SQLAlchemy` | `requirements.txt` 里出现 `django` / `fastapi` / `peewee` / `tornado` | 撤销这行依赖；别在本仓引竞品框架 |

修到 hook 通过为止 —— 这是**最低**质量线，不是 nice-to-have。
