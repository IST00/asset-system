# Middleware Conventions

> 适用范围：所有"基础设施 / 中间件"相关代码 —— Flask extensions、DB、Celery、JWT、健康检查、observability、日志。
> 受众：人类开发者 + LLM 代码生成工具

核心原则：**共享实例集中在 `app/extensions.py`；接入逻辑集中在 `create_app()`；接入一个中间件 = 加一个 extension + 在工厂里 init_app + 在 config 里加环境变量，不要散在业务里**。

---

## 0. 跟 Java 孪生仓的区别

Java 侧有独立仓 `scaffolding-middleware/`（多模块 Maven，产出可选 starter jar）。Python 侧**没有这一层**，原因：

- Flask 的 "中间件" 形态就是 extension（`SQLAlchemy()` / `JWTManager()` / `Migrate()`…），本质是一个对象加一行 `.init_app(app)`，没必要再包一层 starter。
- 可选集成（如 Celery）靠 **环境变量条件装配**：变量没配就不初始化；比 Java 的 `@ConditionalOnProperty` 更简单。
- 真正要跨项目复用的时候，拆成独立 PyPI 包（`pip install ...`），而不是 monorepo 子模块。

**所以：Python 项目里"新增中间件" ≠ 拆 starter，而是 §1 讲的三步法。**

---

## 1. 接入一个新中间件的三步法

1. **声明一个共享实例**：在 `app/extensions.py` 里 `foo = Foo()`。
2. **在工厂里绑定到 app**：在 `app/__init__.py:create_app()` 里 `foo.init_app(app)`，并决定**顺序**（observability → db/jwt → blueprints → error_handlers → cors，不要乱插）。
3. **把配置挂到 `config.py`**：在 `BaseConfig` / `DevConfig` / `ProdConfig` 里读 `os.getenv("...")`；业务里只用 `current_app.config["..."]`，**不要**散写 `os.getenv` 探测。

### 骨架示例（假设新增一个 `flask_caching.Cache`）

```python
# 1. app/extensions.py
from flask_caching import Cache
cache = Cache()
```

```python
# 2. app/__init__.py
from app.extensions import cache

def create_app(config=None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config or load_config())
    init_observability(app)         # traceId 第一
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cache.init_app(app)             # ← 新增，放在 db 和 blueprint 之间
    register_jwt_callbacks(app, jwt)
    from app.api import register_blueprints
    register_blueprints(app)
    register_error_handlers(app)
    _enable_cors(app)
    return app
```

```python
# 3. config.py
class BaseConfig:
    CACHE_TYPE: str = os.getenv("CACHE_TYPE", "SimpleCache")
    CACHE_DEFAULT_TIMEOUT: int = int(os.getenv("CACHE_DEFAULT_TIMEOUT", "300"))
```

```bash
# 4. back/.env.dev 和 back/.env.prod 都加一行，prod 用占位
CACHE_TYPE=SimpleCache
CACHE_DEFAULT_TIMEOUT=300
```

### 反模式

- ❌ 在 blueprint 里 `cache = Cache(app)` 新造一个实例 —— 跟工厂里的那个不是同一个。
- ❌ 在业务代码里散写 `os.getenv("CACHE_TYPE", "SimpleCache")` —— 用 `current_app.config["CACHE_TYPE"]`。
- ❌ 把 init_app 调用写在模块顶层或第一次请求钩子里 —— 时序不可控。

---

## 2. 现有 extension 清单

| extension | 声明 | init 时机 | 配置前缀 / 环境变量 | 开关策略 |
| --- | --- | --- | --- | --- |
| `db` = `SQLAlchemy()` | `app/extensions.py` | `create_app()` | `SQLALCHEMY_*`、`DB_URL` / `DB_HOST` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` / `DB_PORT` | 始终启用；profile 决定 sqlite vs mysql |
| `migrate` = `Migrate()` | 同上 | 同上 | Alembic 目录 `back/migrations/` | 始终启用 |
| `jwt` = `JWTManager()` | 同上 | 同上 | `JWT_SECRET_KEY`（= env `JWT_SECRET`）、`JWT_ACCESS_TOKEN_EXPIRES`（= env `JWT_EXPIRE_SECONDS`）、`JWT_TOKEN_LOCATION`、`JWT_HEADER_NAME`、`JWT_HEADER_TYPE` | 始终启用 |
| `api` = `flask_smorest.Api()` | 同上 | 暂未在工厂里 `init_app`；预留给后续 OpenAPI 集成 | `API_TITLE` / `API_VERSION` / `OPENAPI_*` | 预留 |
| Celery `celery_app` | `app/tasks/__init__.py` | 不在 Flask 进程 init；独立进程 `celery -A app.tasks.celery_app worker` | `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | **可选**：没配 broker URL 时 worker 起不来，Flask 进程不受影响 |

**改这份表 = 改脚手架本体**（见 `workflow.md` §6）。

---

## 3. 可选集成：环境变量为开关（无 Java 风 `@ConditionalOnProperty`，够用就行）

Python 侧的约定是 **"环境变量空 / 未设 ⇒ 不启用"**。这是 `app/health/__init__.py` 和 `config.py` 已经遵守的规则，新增的可选集成务必跟上。

### 3.1 Celery

- `celery_app` 在 `app/tasks/__init__.py` 里构造；broker / backend 从 `config` 拿。
- 没配 `CELERY_BROKER_URL` 时，worker 启动会失败，但 **Flask web 进程完全不受影响**（不要在 web 请求路径里 `send_task`，否则会连上 broker）。
- 任务声明：`@celery_app.task(name="tasks.xxx")`；`name` **必须显式写**，避免 worker 和 web 两端因模块名不一致时找不到任务。
- 调用：业务侧用 `celery_app.send_task("tasks.xxx", args=[...])`；不要直接 `from app.tasks import xxx`（会把 Celery 依赖推到 web 进程启动链）。

---

## 4. 健康检查（`app/health/`）

独立的 Flask app，跑在专用端口（默认 `8081`，bind `0.0.0.0`），由 gunicorn `post_fork` 或 `manage.py run` 的 daemon 线程启动。

### 契约

- `GET /health` —— 聚合所有已注册 check；全过 → `200` + `{status:"UP"}`，有 fail → `503` + `{status:"DOWN"}`。
- `GET /health/liveness` —— 进程活着就 `200`，永不 check 依赖（用于 K8s liveness probe）。
- `GET /health/readiness` —— 同 `/health`，跑全部 check（用于 K8s readiness probe）。
- 响应 `X-Request-ID` 不带 —— health 请求**不**记 access log（见 `observability/__init__.py`）。

### 注册新 check

`register_check(name, fn)`，`fn` 返回 `CheckResult(name, ok, detail={...})`。**必须条件性注册**：对应配置没给就不注册。

```python
# 给 "外部 XX API" 加一个 check
from app.health import register_check, CheckResult

def _check_xx() -> CheckResult:
    # 省略 try/except；register_check 外层有 _timed() 包裹
    import requests, os
    r = requests.get(f"{os.getenv('XX_BASE_URL')}/ping", timeout=2)
    r.raise_for_status()
    return CheckResult("xx", True, {"status": r.status_code})

# 只在配置给了 XX_BASE_URL 时才注册
if (os.getenv("XX_BASE_URL") or "").strip():
    register_check("xx", _check_xx)
```

### 坑

- `db` check 始终注册；数据库不可用时 readiness 返回 503。
- check 里的异常会被 `_timed()` 吞成 `ok=false` —— **不要**自己 try/except 吞掉错误还 return `ok=True`。
- **不要**让 check 依赖 Flask 请求上下文；DB check 通过 `bind_business_app(app)` + `with app.app_context()` 借用业务 app 的上下文。

---

## 5. Observability（`app/observability/`）

只做两件事：**traceId 注入** + **日志对齐 Java 格式**。改这块 = 改脚手架本体。

### 5.1 traceId

- `before_request` 读 `X-Request-ID`；没有就 `uuid4().hex`；塞进 `flask.g.trace_id` 和 thread-local。
- `after_request` 把 `g.trace_id` 写回 `X-Request-ID` 响应头。
- 业务代码**不要**自己算 / 塞 traceId；要在 Celery / CLI 里补 traceId 走 `set_trace_id(trace_id)`。
- MDC 查询值就用 `logging.getLogger(__name__).info("...")`，`MdcFilter` 会自动给 LogRecord 补 `traceId`。

### 5.2 日志格式

模式固定（与 Java `logback-quick-include.xml` 对齐）：

```
%d{yyyy-MM-dd HH:mm:ss.SSS} [%thread] [%X{traceId:-}] %-5level %logger{36} - %msg%n
```

env 旋钮（与 Java `-D` 属性一一对应，具体见 `observability/__init__.py` 头注释）：

| 变量 | 默认 | 对应 Java |
| --- | --- | --- |
| `LOG_FILE` | 空 → 用 `LOG_PATH` 拼 | `-DLOG_FILE` |
| `LOG_PATH` | `logs` | `-DLOG_PATH` |
| `LOG_FILE_BASENAME` | `back` | `QUICK_LOG_ARCHIVE_BASENAME` |
| `LOG_MAX_FILE_SIZE` | `50MB` | `QUICK_LOG_MAX_FILE_SIZE` |
| `LOG_MAX_HISTORY` | `30` | `QUICK_LOG_MAX_HISTORY` |
| `LOG_LEVEL` | `INFO` | `QUICK_LOG_ROOT_LEVEL` |
| `LOG_CONSOLE` | `true` | —— |
| `LOG_FILE_ENABLED` | 非 testing 时 `true`，testing `false` | —— |

### 5.3 不要做

- ❌ 在业务里 `print(...)`：没 traceId、没 level、拉低信号/噪声比。
- ❌ 自己重新 `logging.basicConfig(...)`：工厂已经装好 formatter/handler，覆盖会把 traceId 打丢。
- ❌ 改 `_TEXT_FMT` 格式：跨语言统一是刻意的，改这个 = 改脚手架本体。

---

## 6. CORS

单点在 `app/__init__.py:_enable_cors`，读 `CORS_ALLOWED_ORIGINS`（默认 `*`）。**不要**：

- 在 blueprint 上用 `@cross_origin()` 装饰器散着加。
- 生产环境维持 `*` —— 部署前把 `CORS_ALLOWED_ORIGINS` 改成具体域名。

---

## 7. 新增"中间件"时的 checklist

给自己 / 给 AI 工具的交付清单：

- [ ] `app/extensions.py` 有共享实例（或决定了不需要，在代码注释写清理由）。
- [ ] `app/__init__.py:create_app()` 里 `init_app(app)`，顺序合理。
- [ ] 配置项在 `config.py` 的 `BaseConfig` / `DevConfig` / `ProdConfig` 里读。
- [ ] `back/.env.dev` 和 `back/.env.prod` 都加了条目，`.env.prod` 只放占位。
- [ ] 如果引入 **可选依赖**：环境变量为空时不启用的模式已遵守。
- [ ] 如果可观测：`app/health` 加了条件注册的 check；新 check 读的环境变量空时不注册。
- [ ] `requirements.txt` 钉了具体版本（`==x.y.z`），不要用 `>=`。
- [ ] 更新了本 `middleware.md` 的 §2 清单。

---

## 8. 禁止引入

- ❌ Django / FastAPI / Tornado / Peewee —— 已被 `guard-conventions.sh` 扫 `requirements.txt` 拦截。想用 FastAPI 的依赖注入风格？在现有 Flask 侧靠 service 单例 + 显式参数实现。
- ❌ 其它多框架并存（Flask + FastAPI 同进程）。
- ❌ 把业务代码塞进 `app/health/`、`app/observability/`、`app/extensions.py` —— 这三个目录是基础设施，**不放业务**。
