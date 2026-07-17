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
python manage.py run [dev|prod]                            # 启动开发服务器
```

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
- MySQL：3306

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
