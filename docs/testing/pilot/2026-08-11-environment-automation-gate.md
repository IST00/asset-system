# 环境与自动化质量门禁记录

> 本记录来自本地受限环境的当前工作区诊断，不代表独立 pilot 环境验收通过。不得据此连接生产或安排上线。

| 字段 | 内容 |
| --- | --- |
| 阶段 | 环境与安全 / 自动化质量 |
| 候选版本 | `cf831166e9c458a8ef9c4fe38d92a48e0d203e68`；工作区有未提交改动，尚未冻结 |
| 镜像 | 未生成 |
| 环境 | local diagnostic；pilot 未建立 |
| 数据库身份 | 仅验证 pilot/prod 示例身份不同，未连接数据库 |
| 模拟数据快照 | 未装载 |
| Python / pip | 3.12.11 / 25.0.1，均不符合冻结要求 |
| Node / npm | 22.23.1 / 10.9.8，符合冻结要求 |
| MySQL | 未连接；8.4/utf8mb4/UTC 待 pilot 验证 |
| 锁文件 | `front/package-lock.json` 存在；根 npm 与 Python 哈希锁缺失 |
| 执行人 | Codex 自动化诊断 |
| 执行时间 | 2026-08-11T00:53:39+08:00 |

## 准入检查

- [ ] 候选版本、锁文件和镜像已冻结
- [ ] Python 3.13 与 pip 25.2 已就绪
- [ ] 独立 pilot MySQL、账号和密钥已就绪
- [x] Node 22.23.1 与 npm 10.9.8 已就绪
- [x] pilot/prod 示例数据库身份不同
- [x] 证据不含密码、Token 或连接串

## 自动化结果

| 检查项 | 结果 | 证据摘要 | 缺陷编号 |
| --- | --- | --- | --- |
| Ruff 规则 | PASS | `All checks passed` | — |
| Ruff 格式 | PASS | 210 files formatted | — |
| Mypy | PASS | 131 source files, 0 issues | — |
| 后端业务回归 | PASS | 排除锁文件契约后 `696 passed` | — |
| 后端覆盖率诊断 | READY_FOR_RETEST | 总覆盖率 89%；`asset_management_service.py` 85%，定向 `22 passed`；详见 `coverage-baseline.md` | PILOT-008 |
| 新增环境/安全/UTC 契约 | PASS | 含无 Redis/部署配置契约，`37 passed` | — |
| 环境锁定契约 | FAIL | `10 passed, 3 failed` | PILOT-001 |
| 前端类型检查 | PASS | TypeScript exit 0 | — |
| 前端 ESLint | PASS | 0 errors, 0 warnings | — |
| 前端单元测试 | PASS | `59 passed` | — |
| 前端生产构建 | PASS | Vite production build exit 0 | — |
| 时区直调扫描 | PASS | 无剩余命中 | — |
| Compose 配置渲染 | PASS | 两个服务均为 UTC，示例变量正确展开 | — |
| Compose 健康依赖 | PASS（代码级） | 契约测试与 `docker compose config` 已确认 healthcheck、healthy dependency 和 restart；容器运行待复验 | PILOT-002 |
| 环境身份隔离脚本 | PASS | pilot and production identities are distinct | — |
| 健康/状态接口测试 | PASS | `8 passed` | — |
| 工程约定扫描 | PASS | 155 个 API 路由仅使用 GET/POST；无 Blueprint 越层、前端裸请求或深层相对导入 | — |
| 凭据形态扫描 | PASS（静态） | 无私钥或云访问密钥形态；连接串命中均位于测试、localhost 或占位配置 | — |
| 正式飞书能力审计 | FAIL（上线范围） | 仅有本地模拟和通用回调内核；无 SSO、组织同步、真实客户端、安全回调入口或正式通知 | PILOT-004 |
| 备份恢复能力审计 | FAIL | 仅有环境变量状态展示；无数据库/附件同批次备份、保留、恢复实现和演练证据 | PILOT-005 |
| 业务异步任务审计 | FAIL（上线范围） | Celery 仅有 `tasks.sample_add`；无业务任务、beat 计划和 worker/beat 部署 | PILOT-006 |
| 故障告警能力审计 | FAIL（上线范围） | 无备份/同步/回调失败告警实现、持久化记录和送达演练 | PILOT-007 |
| 调拨/报废审批契约 | FAIL | API 直接提交资产变更，未创建内部审批、审批任务或审批锁 | PILOT-009 |
| 维修/报废金额契约 | READY_FOR_RETEST | 当前工作区已拒绝负维修金额，报废金额改为必填且非负，前端同步必填 | PILOT-010 |
| 公共使用对象契约 | READY_FOR_RETEST | 当前工作区改为 6 位流水号并拒绝创建/更新空白名称 | PILOT-011 |
| 依赖与镜像漏洞扫描 | BLOCKED | 锁文件未完成且漏洞库无法联网更新，不能写“未发现漏洞” | PILOT-001 |
| 干净安装 | BLOCKED | 两个锁文件缺失，注册表访问审批服务返回 401 | PILOT-001 |
| Docker 无缓存构建 | BLOCKED | `back/Dockerfile` 依赖缺失的 `requirements.lock` | PILOT-001 |
| 浏览器冒烟 | BLOCKED | 受限环境禁止监听端口，权限审批服务返回 401 | — |

## 缺陷统计

| P0 | P1 | P2 | P3 |
| ---: | ---: | ---: | ---: |
| 0 | 8 | 2 | 1 |

## 出口结论

- [ ] 通过，可进入核心业务人工验收
- [x] 阻断：进入核心业务人工验收前修复 PILOT-001、PILOT-005、PILOT-009，复验 PILOT-002、PILOT-008、PILOT-010、PILOT-011，并在独立 pilot 环境重新执行本阶段；PILOT-004、PILOT-006、PILOT-007 另行阻断正式上线评审

结论说明：业务测试和覆盖率已改善，但候选版本尚不可重复安装或构建，备份恢复缺失，且调拨/报废会绕过规定审批直接改资产，不能进入独立 pilot 的核心业务人工验收。模拟 pilot 不连接真实第三方；正式飞书、业务调度和故障告警必须在上线评审前另行实现并验证。

业务负责人：________　系统管理员：________　技术负责人：________
