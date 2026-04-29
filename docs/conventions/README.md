# Conventions（Python 脚手架）

> 这里是 `scaffolding-python/` 的编码约定文档集。
> **唯一事实源**：本目录下的四篇。项目根 `CLAUDE.md` 只列高压线；细节全在这里。

| 文档 | 适用范围 |
| --- | --- |
| [`backend.md`](./backend.md) | `back/app/**`（Flask + SQLAlchemy + marshmallow + flask_jwt_extended） |
| [`frontend.md`](./frontend.md) | `front/src/**`（React + TS + Vite + AntD） |
| [`middleware.md`](./middleware.md) | 中间件接入（Flask extensions、DB、Redis、Celery、健康检查、observability） |
| [`workflow.md`](./workflow.md) | 提交 / 分支 / 钩子 / CI / 脚手架自身的变更流程 |

## 给 AI 编码工具（Claude Code / Cursor / Copilot 等）

1. 动手前先读与你任务最相关的那一篇；写代码前 **先读一个同类型的现有文件** 当模板（`api/auth.py`、`services/auth_service.py`、`repositories/user_repository.py`、`front/src/pages/Login.tsx` 等）。
2. 引类 / 导模块前先用 `Grep` 确认存在，**不要瞎猜** import 路径。
3. 改完跑自检：
   - 后端：`cd back && ruff check . && ruff format --check . && mypy app/ config.py && pytest`
   - 前端：`cd front && npm run type-check && npm run lint && npm run build`
4. 违反约定时，`.husky/pre-commit` 里的 [`scripts/guard-conventions.sh`](../../scripts/guard-conventions.sh) 会在提交时直接拦下来。**禁止**用 `--no-verify` 绕过，改完再提交。

## 与 Java 孪生仓的关系

`scaffolding-python/` 是 `scaffolding-java/` 的 Python 孪生。分层原则、统一响应信封、JWT 语义、profile 模型都刻意保持对齐；具体落地（Spring Boot → Flask、MapStruct → marshmallow、Flyway → Alembic、starter → Flask extension）自然不同。遇到差异时，**以 Python 文档为准**，不要反向套用 Java 的类名或注解。
