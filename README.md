# Scaffold Python

React + TypeScript + Flask 全栈脚手架（Python 版）。是 `../scaffolding-java/` 的 Python 孪生：前端完全一致，后端用 **Flask 3 / SQLAlchemy / Flask-JWT-Extended / Alembic / Gunicorn** 替代 Spring Boot / MyBatis-Plus / Flyway。

## 使用说明

- 飞书 Wiki：https://h9f4zz91q9.feishu.cn/wiki/RqUgwZwuxiYMGgkPXo7cAYSZnsd

## 技术栈

**后端**：Python 3.13 · Flask 3 · SQLAlchemy 2 · Flask-Migrate (Alembic) · Flask-JWT-Extended · Flask-Smorest (OpenAPI) · passlib[bcrypt] · Celery · Gunicorn · SQLite/MySQL

**前端**：React 18 · TypeScript · Vite 5 · React Router 6 · Zustand · TanStack Query · Axios · Ant Design 5 · React Hook Form + Zod · lucide-react · i18next

**工程化**：Ruff + Mypy + Pytest · ESLint + Prettier · EditorConfig · Husky + lint-staged · Commitlint · GitHub Actions · Docker + docker-compose

## 目录结构

```
.
├── back/                           # Flask 后端
│   ├── app/
│   │   ├── __init__.py             # create_app 工厂
│   │   ├── extensions.py           # db / migrate / jwt / api 扩展实例
│   │   ├── common/                 # Result / ResultCode / BusinessException / 全局错误处理
│   │   ├── models/                 # SQLAlchemy 模型
│   │   ├── schemas/                # marshmallow DTO
│   │   ├── api/                    # 蓝图（blueprints）
│   │   ├── services/               # 业务逻辑
│   │   ├── security/               # JWT 回调 / 角色守卫
│   │   ├── health/                 # 独立 Flask 健康检查 app（端口 8081）
│   │   └── tasks/                  # Celery 任务
│   ├── migrations/                 # Alembic 迁移
│   │   └── versions/001_init.py
│   ├── tests/                      # pytest
│   ├── config.py                   # Dev/Prod/Test 配置
│   ├── manage.py                   # Flask CLI 入口
│   ├── wsgi.py                     # Gunicorn 入口
│   ├── gunicorn.conf.py            # Gunicorn + post_fork 健康线程
│   ├── pyproject.toml              # ruff / mypy / pytest 配置
│   └── requirements.txt
│
├── front/                          # React + Vite 前端（与 Java 版一致）
│   ├── src/...
│   ├── .env.development            # VITE_API_TARGET=http://localhost:8080
│   ├── .env.production
│   └── vite.config.ts
│
├── .github/workflows/ci.yml
├── .husky/                         # git hooks
├── scripts/guard-conventions.sh    # 反模式守护
├── docker-compose.yml              # mysql + back + front
└── package.json                    # husky + commitlint + lint-staged
```

## 快速开始

### 本地开发

**后端**（SQLite，零外部依赖）：

```bash
cd back
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
FLASK_APP=manage.py flask db upgrade            # 首次执行，建表并写入 admin 种子
python manage.py run dev                         # 启动本地开发服务器
```

`back/.env.dev` 只包含本地模拟配置，数据库固定使用默认的 `back/instance/dev.db`，不需要 MySQL。开发用密钥不得复制到试运行或生产环境。

环境里面如何操作

- 应用：http://localhost:8080
- Swagger：http://localhost:8080/swagger-ui（需显式启用 flask-smorest Api；默认已装）
- 健康检查（独立端口）：http://localhost:8081/health

**前端**：

```bash
cd front
npm install
npm run dev
```

- 前端：http://localhost:3000
- 内置账号：`admin` / `admin123`

### Docker 一键起

```bash
npm run docker:up
```

- 前端：http://localhost
- 后端：http://localhost:8080
- 数据库：外部 MySQL（通过被忽略的部署 env 文件或部署环境提供）

### 小范围试运行与生产配置

仓库中的 `back/.env.prod`、`back/.env.pilot.example` 和 `back/.env.deploy.example` 只保留占位值。真实的 `SECRET_KEY`、`JWT_SECRET` 和数据库密码必须由部署环境或密钥管理器注入；进程环境变量始终覆盖 dotenv 文件。

试运行环境可从模板准备一个已被 Git 忽略的文件：

```bash
cp back/.env.pilot.example back/.env.pilot
# 由部署平台注入真实密钥和数据库密码，并补齐其余占位项后再启动
cd back
FLASK_ENV=prod ENV_FILE="$PWD/.env.pilot" python manage.py run
```

生产环境使用部署平台注入，或从 `back/.env.deploy.example` 准备被忽略的 `back/.env.deploy`。Gunicorn 启动方式：

```bash
cd back
FLASK_ENV=prod gunicorn -c gunicorn.conf.py wsgi:app
```

部署要求：

- `DEPLOYMENT_STAGE=pilot` 或 `production` 会启用启动时安全门禁；占位密钥、占位/非 MySQL 数据库配置、通配 CORS、非 HTTPS CORS 都会拒绝启动。
- 生产 CORS 必须显式列出 HTTPS 来源，禁止使用 `*`。
- 试运行与生产必须使用不同的 `DB_USER` 和 `DB_NAME`，并分别授予最小权限。
- 部署前从仓库根运行 `back/.venv/bin/python scripts/check_environment_isolation.py back/.env.pilot back/.env.deploy`。
- 应用访问日志不记录查询字符串、Authorization、请求体或附件内容，日志 formatter 还会脱敏常见密码、Token 和数据库连接串。
- 仓库清除凭据不会自动轮换数据库账号；实际轮换和旧账号撤销必须由数据库/平台管理员执行。

完整步骤见 [数据库凭据轮换与环境隔离操作手册](docs/runbooks/security-credential-rotation.md)。

## 后端接口

| Method | Path               | Auth  | 说明           |
| ------ | ------------------ | ----- | -------------- |
| POST   | /api/auth/register | 否    | 注册           |
| POST   | /api/auth/login    | 否    | 登录，返回 JWT |
| GET    | /api/hello         | 否    | 健康测试       |
| GET    | /api/users/me      | 是    | 当前用户       |
| GET    | /api/users         | ADMIN | 用户分页列表   |

统一返回结构：`{ "code": 200, "message": "OK", "data": { } }`（同 Java 版）。

## 与 Java 版的映射

| Java 版                         | Python 版                             |
| ------------------------------- | ------------------------------------- |
| Spring Boot 3.3                 | Flask 3                               |
| MyBatis-Plus                    | SQLAlchemy 2                          |
| Flyway (`V{n}__*.sql`)          | Alembic (`migrations/versions/*.py`)  |
| Spring Security + jjwt          | Flask-JWT-Extended                    |
| springdoc-openapi               | flask-smorest                         |
| BCryptPasswordEncoder           | passlib[bcrypt]                       |
| H2（dev）/ MySQL（prod）        | SQLite（dev）/ MySQL（prod）          |
| Actuator 独立端口               | 独立 Flask health app（threading）    |
| Maven                           | pip + pyproject.toml                  |
| JUnit + MockMvc                 | pytest + Flask test client            |
| Logback                         | Python logging                        |
| —                               | Celery（异步任务）                    |
| —                               | Gunicorn（WSGI）                      |

## 提交规范

Conventional Commits，同 Java 版。`feat / fix / docs / style / refactor / perf / test / build / ci / chore / revert`。

## License

MIT
