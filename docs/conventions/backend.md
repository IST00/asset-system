# Backend Conventions (`back/`)

> 适用范围：`scaffolding-python/back/app/**` + `back/config.py` + `back/migrations/**`
> 受众：人类开发者 + LLM 代码生成工具

核心原则：**严格分层 + 统一响应信封 + Schema 边界**。违反下面任何一条会被 `scripts/guard-conventions.sh` 在 pre-commit 里拦截；强行绕过 = 破坏脚手架约束。

---

## 1. 分层与依赖方向

```
api (blueprint)  →  services  →  repositories  →  models (SQLAlchemy)
                        ↘  schemas (入/出参) ↗
```

实际包映射：`app/api/`、`app/services/`、`app/repositories/`、`app/models/`、`app/schemas/`、`app/common/`、`app/security/`。

- `api/*`（blueprint）**只**能调 `services/*`；**禁止** `from app.models import ...`，**禁止** `from app.extensions import db`，**禁止**直接写 `db.session.*`。
- `services/*` 是业务中心，拥有事务边界：构造 SQLAlchemy 过滤器、调 `repositories/*`、必要时 `db.session.commit()`。`services` 之间允许互调。
- `repositories/*` 只管 "怎么查/怎么写" 一个聚合；不抛 `BusinessException`、不提交事务（commit 归 service）。`repositories/base.py:BaseRepository` 提供泛型 CRUD + `QuerySpec` 分页；领域查询在子类里加方法（参考 `UserRepository.find_by_username`）。
- `models/*` = `db.Model` 子类；时间戳通过 `app/models/mixins.py:TimestampMixin` 注入。
- `schemas/*` = marshmallow `Schema`；是 DTO 边界，**entity 永远不能越过 blueprint**，必须转字典 / 经 `*Schema.dump(...)` 才能出 API。

### ✅ 正确

```python
# app/api/users.py
from flask import Blueprint
from flask_jwt_extended import get_jwt_identity, jwt_required
from app.common import Result
from app.services import user_service

bp = Blueprint("users", __name__, url_prefix="/api/users")

@bp.get("/me")
@jwt_required()
def me() -> dict:
    username = get_jwt_identity()
    return Result.success(user_service.get_current(username)).to_dict()
```

### ❌ 错误

```python
# blueprint 直连 model / db，跨过 service
from app.extensions import db          # ❌ 跨层
from app.models import User            # ❌ 跨层

@bp.get("/me")
@jwt_required()
def me() -> dict:
    u = db.session.scalar(select(User).where(User.username == get_jwt_identity()))
    return Result.success({"id": u.id, "username": u.username}).to_dict()
```

上面的 `from app.models ...` 与 `from app.extensions import db` 会被 `guard-conventions.sh` 命中并拦住提交。

---

## 2. 统一响应协议

所有 REST 接口返回 **`Result` 信封** `{ code, message, data }`；分页用 `PageResult` 包在 `Result.data` 里。实现见 `app/common/result.py`、`app/common/errors.py`。

- 成功：`Result.success(data).to_dict()` / `Result.success().to_dict()`。
- 失败：**在 service 层抛 `BusinessException`**，**不要**在任何地方手写 `Result.fail(...)`。全局 `register_error_handlers`（`app/common/errors.py`）会把 `BusinessException` / `ValidationError` / `HTTPException` 翻译成信封。
- 状态码：从 `ResultCode` 枚举取（`SUCCESS / BAD_REQUEST / UNAUTHORIZED / FORBIDDEN / NOT_FOUND / INTERNAL_ERROR / BUSINESS_ERROR`）；**不要**在业务里散写裸整数。

### ✅

```python
# services/auth_service.py
from app.common import BusinessException, ResultCode

if user_repository.username_exists(username):
    raise BusinessException("username already exists")           # 默认 BUSINESS_ERROR

if not verify_password(password, user.password):
    raise BusinessException("invalid credentials", result_code=ResultCode.UNAUTHORIZED)
```

### ❌

```python
# api/auth.py
if taken:
    return Result.fail(400, "用户已存在").to_dict()               # ❌ 绕过 BusinessException
                                                                 #   guard-conventions.sh 会拦
```

### 为什么必须抛异常而不是返回

service 里一旦 `return Result.fail(...)`，调用方要么得自己再判状态码再跳转，要么忘了判 → 把错误当成功继续往下走。抛异常让控制流在错误出现的位置终止，handler 统一翻成信封，blueprint 永远只处理 happy path。

---

## 2.5. HTTP 动词只用 GET 与 POST

脚手架的 blueprint **只允许** `@bp.get(...)` 和 `@bp.post(...)` 两种装饰器。

- **`@bp.get(...)`** —— 幂等查询；入参走 `request.args` / 路径参数，不读 body。
- **`@bp.post(...)`** —— 其他一切（创建 / 更新 / 删除 / 动作 / 批量操作）；入参走 `request.get_json(...)` 经 `*RequestSchema.load(...)` 校验。

**禁止使用**：`@bp.put` / `@bp.delete` / `@bp.patch`；也禁止 `@bp.route(..., methods=["PUT","DELETE","PATCH"])` 或 `add_url_rule(..., methods=["PUT", ...])`。

### 为什么

- **LLM 生成代码一致性**：减少 AI 工具在 "用 PUT 还是 POST" 之间摇摆，约束少 = 生成更稳。
- **网关 / 代理兼容**：老旧代理、部分 WAF、公司内网穿透对 PUT/DELETE/PATCH 的支持不如 GET/POST 稳。统一收敛到两种，部署面最小。
- **前端对接简单**：`@/api/http` 统一用 `get` / `post`；不再有 "业务到底用 delete 还是 post" 的反复拉扯。
- **幂等语义自己担保**：REST 的 PUT/DELETE 幂等只是"协议层约定"，真实幂等要 service 里做去重 / 条件更新。不靠 HTTP 动词。

### URL 命名约定（动作化，弥补动词收敛）

因为不再靠动词表达语义，URL 末段用动词或 `/action` 后缀表达意图：

```
GET  /api/users                         # 列表查询（分页走 query param）
GET  /api/users/<int:id>                # 单个查询
POST /api/users                         # 创建
POST /api/users/<int:id>/update         # 更新
POST /api/users/<int:id>/delete         # 删除
POST /api/users/<int:id>/disable        # 领域动作
POST /api/users/batch-import            # 批量
```

### ✅

```python
# app/api/users.py
from flask import Blueprint, request
from flask_jwt_extended import jwt_required
from app.common import Result
from app.schemas.user import (
    CreateUserRequestSchema,
    UpdateUserRequestSchema,
)
from app.services import user_service

bp = Blueprint("users", __name__, url_prefix="/api/users")

_create_schema = CreateUserRequestSchema()
_update_schema = UpdateUserRequestSchema()


@bp.get("")
@jwt_required()
def page() -> dict:
    page_num = int(request.args.get("page", 1))
    size = int(request.args.get("size", 20))
    return Result.success(user_service.page(page_num, size)).to_dict()


@bp.get("/<int:user_id>")
@jwt_required()
def detail(user_id: int) -> dict:
    return Result.success(user_service.get(user_id)).to_dict()


@bp.post("")
@jwt_required()
def create() -> dict:
    payload = _create_schema.load(request.get_json(silent=True) or {})
    return Result.success(user_service.create(payload)).to_dict()


@bp.post("/<int:user_id>/update")
@jwt_required()
def update(user_id: int) -> dict:
    payload = _update_schema.load(request.get_json(silent=True) or {})
    return Result.success(user_service.update(user_id, payload)).to_dict()


@bp.post("/<int:user_id>/delete")
@jwt_required()
def delete(user_id: int) -> dict:
    user_service.delete(user_id)
    return Result.success().to_dict()
```

### ❌

```python
@bp.put("/<int:user_id>")                # ❌ 禁用 PUT
def update(user_id: int): ...

@bp.delete("/<int:user_id>")             # ❌ 禁用 DELETE
def delete(user_id: int): ...

@bp.patch("/<int:user_id>/status")       # ❌ 禁用 PATCH
def patch(user_id: int): ...

@bp.route("/<int:user_id>",
          methods=["DELETE"])            # ❌ 换写法也不行
def del_user(user_id: int): ...
```

前端对应（`@/api/http`）：**只**用 `http.get(...)` / `http.post(...)`，不写 `http.put` / `http.delete` / `http.patch`。

---

## 3. Schema 边界（marshmallow）

- 入参：`*RequestSchema.load(request.get_json(silent=True) or {})`。`ValidationError` 会被全局 handler 翻成 `400 + Result.fail(BAD_REQUEST, ...)`。
- 出参：`*ResponseSchema.dump(entity_or_dict)`；或者 service 直接返回已序列化的 `dict[str, Any]`（当前代码里的做法，见 `auth_service._user_to_dict` / `user_service._user_to_dict`）。**entity 实例不能越过 service 边界返回给 blueprint**。
- Schema 统一放在 `app/schemas/`，一个领域一个文件（`schemas/user.py`）；在 `app/schemas/__init__.py` re-export。
- 字段校验尽量写在 schema（`validate.Length` / `validate.Range` / 自定义 validator），不要在 service 里再重复校验长度、类型。

### ✅

```python
# app/api/auth.py
_login_schema = LoginRequestSchema()            # 模块级复用一个实例

@bp.post("/login")
def login() -> dict:
    payload = _login_schema.load(request.get_json(silent=True) or {})
    data = auth_service.login(username=payload["username"], password=payload["password"])
    return Result.success(data).to_dict()
```

### ❌

```python
# 手写校验 + 直接 return entity
@bp.post("/login")
def login():
    data = request.get_json() or {}
    if len(data.get("username", "")) < 3:                    # ❌ 重复校验
        return jsonify({"code": 400, "message": "bad"}), 400 # ❌ 绕开信封
    user = auth_service.login(...)                           # 假设它返回 User entity
    return user                                              # ❌ entity 穿透到 HTTP
```

---

## 4. 持久化 & 迁移（SQLAlchemy + Alembic）

- ORM 统一 **SQLAlchemy 2.x**（`sqlalchemy.orm.Mapped` / `mapped_column`），持久化通过 `Flask-SQLAlchemy` 的 `db`。
- **禁止**引入 Django ORM、FastAPI 的依赖体系、Peewee、Tortoise —— `guard-conventions.sh` 会扫描 `back/requirements.txt` 并拦截。
- Schema 变更**必须**走 Alembic：`FLASK_APP=manage.py flask db migrate -m "..."` 生成，再 `flask db upgrade` 应用。迁移文件命名严格匹配正则 `^[0-9]{3,}_[a-z0-9_]+\.py$`（见 `001_init.py`）。
- **已合入主干的迁移文件不能改内容**；要修只能追加 `{n+1}_<snake>.py` 的新迁移做回滚或补丁。
- 事务：service 在成功路径末尾调 `db.session.commit()`；repository 只 `session.add(...)` + `flush()`。异常路径由全局 handler 捕获，Flask-SQLAlchemy 默认在请求结束时 rollback；不要手写 `try/except/rollback`。

### ✅

```
back/migrations/versions/
├── 001_init.py
├── 002_add_user_email.py          # 新增列
└── 003_backfill_user_email.py     # 数据回填
```

### ❌

```
├── 001_init.py
├── 001_1_add_user_email.py        # ❌ 命名违规，guard 会拦
└── 001_init_again.py              # ❌ 重复序号；已合入的不能改
```

---

## 5. 安全 & JWT

- 签发 / 校验 token 一律走 `flask_jwt_extended`（`create_access_token`、`@jwt_required()`、`get_jwt_identity()`、`get_jwt()`）。
- **禁止** 在 `api/*` 或 `services/*` 里 `import jwt`、`from jose import jwt`、自己切 `Authorization` 头解码 —— `guard-conventions.sh` 会拦 `jwt.decode` / `PyJWT` / `jose.jwt`。需要自定义签发 / 解析逻辑，写在 `app/security/*`。
- 角色鉴权：`app/security/jwt_callbacks.py:require_role("ADMIN", get_jwt())`；需要保护的接口加 `@jwt_required()`，角色不足抛 `BusinessException(result_code=ResultCode.FORBIDDEN)`。
- 默认放行列表：`/api/auth/login`、`/api/auth/register`、`/api/hello`（blueprint 上不加 `@jwt_required()` 就是放行）。要让全站默认鉴权，请先和团队对齐再改。
- 密码：`app/security/passwords.py` 的 `hash_password` / `verify_password`（底层 `bcrypt`）。**不要**自己拼 sha256 / md5。

### ✅

```python
@bp.get("")
@jwt_required()
def page_users() -> dict:
    if not require_role("ADMIN", get_jwt()):
        raise BusinessException(result_code=ResultCode.FORBIDDEN)
    ...
```

### ❌

```python
@bp.get("/me")
def me():
    bearer = request.headers["Authorization"]
    payload = jwt.decode(bearer.split()[1], SECRET, algorithms=["HS256"])  # ❌ 自己解
    ...
```

---

## 6. 配置 & Profile

配置由两层组合（见 `config.py` 头注释）：

1. **profile 类**（`DevConfig` / `ProdConfig` / `TestConfig`）—— 真实的 Flask config 对象。
2. **profile dotenv 文件** —— 按 profile 自动加载，**已进 git**。

| Profile | 对应文件 | 典型场景 |
| --- | --- | --- |
| `dev` / `development`（默认） | `back/.env.dev` | 本地开发；sqlite `instance/dev.db` |
| `prod` / `production` | `back/.env.prod` | 生产；MySQL；**所有机密**必须在部署环境覆盖 |
| `test` / `testing` | `back/.env.dev` | pytest；内存 sqlite；共享 dev 的 .env |

### 加载规则（`config.bootstrap_env`）

- **系统环境变量永远 > dotenv 文件**（`load_dotenv(env_file, override=False)`）。容器 / K8s Secret / systemd EnvironmentFile 注入的机密不会被 `.env.prod` 里的占位值覆盖。
- `.env.prod` 进 git，**只放占位值**（`CHANGE_ME_IN_DEPLOYMENT`），真实机密靠部署环境注入。
- `ENV_FILE=/path/to/file` 可显式指定 dotenv 文件，越过 profile 映射。

### 启动时切 profile（四种形式等价）

```bash
python manage.py run                       # 默认 dev
python manage.py run prod                  # 位置参数（Java 风格）
python manage.py run --env prod            # flag 形式
FLASK_ENV=prod python manage.py run        # 环境变量

# 生产（gunicorn）
FLASK_ENV=prod gunicorn -c gunicorn.conf.py wsgi:app
```

### 新增环境变量

1. 在 `back/.env.dev` 和 `back/.env.prod` **都**加一行；后者放占位。
2. 在 `config.py` 的 `BaseConfig` / `DevConfig` / `ProdConfig` 里读 `os.getenv("X", default)`。
3. 不要在业务代码里散写 `os.getenv("MY_NEW_VAR")` —— 走 `current_app.config["MY_NEW_VAR"]`。

---

## 7. 包结构与命名

| 目录 | 放什么 | 命名 |
| --- | --- | --- |
| `app/api/` | blueprint，一文件一资源 | `auth.py`、`users.py`（蛇形；文件名 = 资源名） |
| `app/services/` | 业务逻辑，一文件一领域 | `auth_service.py`、`user_service.py`（`_service` 后缀） |
| `app/repositories/` | 数据访问，一文件一 aggregate | `user_repository.py`（`_repository` 后缀）；导出 `user_repository` 小写单例 |
| `app/models/` | SQLAlchemy 模型 | `user.py`；类名 `User`（名词，不带 `Entity`） |
| `app/schemas/` | marshmallow schema | `user.py`；类名 `*RequestSchema` / `*ResponseSchema` |
| `app/common/` | 信封 / 错误类 / 全局 handler | 不放业务 |
| `app/security/` | JWT 回调、密码、角色 | 不放业务 |
| `app/health/` | 独立健康检查 app（见 [middleware.md](./middleware.md)） | 仅基础设施 |
| `app/observability/` | traceId + 日志（见 [middleware.md](./middleware.md)） | 仅基础设施 |
| `app/tasks/` | Celery app 与任务 | `celery_app` + `@celery_app.task` |

新模块（如 `order`）：在 `api/order.py` / `services/order_service.py` / `repositories/order_repository.py` / `models/order.py` / `schemas/order.py` 各开一个文件，不要新发明子包层级。

---

## 8. 测试约定

- `back/tests/` 下用 **pytest**；文件名 `test_*.py`，用例名 `test_*`。
- 用 `TestConfig`（内存 sqlite），启动时 `create_app(TestConfig)`；不要污染 `instance/dev.db`。
- 涉及 DB 的用例用 `app.test_client()` + `db.create_all()`；集成完毕 `db.drop_all()` 或使用 fixture 自动回滚。
- 运行：`cd back && pytest`；单用例：`pytest tests/test_auth.py::test_register_and_login`。
- 新写的 service / repository / blueprint **必须**至少一条用例（happy + 一个 failure），否则审核不过。

---

## 9. Lint / 类型检查

| 工具 | 命令 | 门槛 |
| --- | --- | --- |
| Ruff（lint + format 检查） | `ruff check . && ruff format --check .` | **零告警** |
| mypy | `mypy app/ config.py` | **零错误**，禁 `Any` 除非加 `# type: ignore[...] — 原因` |
| pytest | `pytest` | 改到的代码必须绿 |

Push 前最小自查：

```bash
cd back && ruff check . && ruff format --check . && mypy app/ config.py && pytest
```

不要用 `# noqa` / `# type: ignore` 静默告警；确需静默时必须在行尾写清理由。

---

## 10. 快速对照（Java 孪生）

| 概念 | Java 侧 | Python 侧 |
| --- | --- | --- |
| 统一信封 | `common.Result<T>` | `app.common.Result` |
| 状态码 | `common.ResultCode` enum | `app.common.ResultCode` Enum |
| 领域异常 | `exception.BusinessException` | `app.common.BusinessException` |
| 入/出参 | DTO + MapStruct | marshmallow `*RequestSchema` / `*ResponseSchema` |
| ORM | MyBatis-Plus `BaseMapper<T>` | SQLAlchemy 2.x + `BaseRepository[M]` |
| 迁移 | Flyway `V{n}__*.sql` | Alembic `{NNN}_<snake>.py` |
| JWT | `JwtAuthFilter` + `JwtUtil` | `flask_jwt_extended` + `app/security/jwt_callbacks.py` |
| Profile | Spring profile + argv `PROD` | `FLASK_ENV` + argv `prod` + `bootstrap_env()` |

遇到 Java 有、Python 暂时没做的东西（例如 `@Validated` 的 group、`@Transactional`）：不要硬塞类似的装饰器，按 Python 侧的现有手法解决（schema 里加条件 validator、service 里明确 `db.session.commit()`）。
