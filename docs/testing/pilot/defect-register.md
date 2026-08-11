# 试运行缺陷登记

| 编号 | 发现阶段 | 严重级别 | 复现步骤 | 期望结果 | 实际结果 | 负责人 | 修复版本 | 回归用例 | 状态 | 截止日期 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PILOT-001 | 环境与自动化质量 | P1 | 执行 `back/.venv/bin/python scripts/check_toolchain.py` 和 `back/.venv/bin/python -m pytest back/tests/test_environment_contract.py -q` | Python 3.13/pip 25.2、三个锁文件齐备且环境契约通过 | Python 3.12.11/pip 25.0.1；根 `package-lock.json` 与 `back/requirements.lock` 缺失，前端 lock 与精确 manifest 不一致；契约 3 项失败 | 待分配 | — | `back/tests/test_environment_contract.py` + `scripts/verify-clean-install.sh` | OPEN | 试运行前 |
| PILOT-002 | 环境与自动化质量 | P2 | 以部署示例环境执行 `docker compose config` | 后端有 readiness healthcheck，前端等待后端 healthy，服务有明确重启策略 | 当前工作区已补齐并通过 Compose 契约与配置渲染；待镜像运行复验 | 待分配 | 当前未提交工作区 | `test_compose_uses_health_aware_startup_and_restart_policies` + 容器运行复验 | READY_FOR_RETEST | 试运行前 |
| PILOT-003 | 品牌与易用性 | P3 | 扫描并检查 `front/src/features/operations/Notifications.tsx` 的页面标题和说明 | 页面使用面向业务用户的已批准文案，不出现开发待办或实现说明 | 页面仍显示 `TODO CENTER`，并描述“演示消息”和“尚未建设”的内部实现边界 | 待分配 | — | 品牌扫描 + 通知页桌面/手机人工复验 | OPEN | 品牌验收前 |
| PILOT-004 | 正式上线准备 / 飞书 | P1 | 在 `back/app`、迁移和测试中搜索飞书 OAuth、组织同步、OpenAPI 客户端、签名验签和回调解密，并检查已注册 Blueprint | 第一版正式使用具备飞书 SSO、员工/部门同步、安全回调和真实通知，且状态接口只在能力实测成功后报告可用 | 只有开发/测试环境的本地审批模拟与通用回调内核；无正式飞书 Blueprint、客户端、身份字段/同步任务、签名验签或解密实现；`system_status_service` 仅凭 App ID/Secret 判断“正式已配置” | 待分配 | — | 飞书沙箱契约测试 + 错误签名/重复事件测试 + SSO/组织同步/领退/通知人工验收 | OPEN | 正式上线评审前 |
| PILOT-005 | 正式上线准备 / 备份恢复 | P1 | 在应用、脚本、Compose 和任务注册中搜索数据库/附件备份、保留清理、恢复和恢复核对实现 | 数据库与附件按同一批次自动备份，保留 30 天，保存到隔离介质，并可在独立恢复库完成恢复和关键数据核对 | 只有环境变量是否存在的状态展示；无备份/恢复脚本、批次记录、保留策略、定时执行、恢复校验或恢复演练证据；单个相关变量即可被状态接口报告为“已配置” | 待分配 | — | 备份契约测试 + 独立恢复库演练 + 关键表计数/附件摘要核对 | OPEN | 试运行前 |
| PILOT-006 | 正式上线准备 / 定时任务 | P1 | 检查 `back/app/tasks`、Celery 注册任务、beat 配置和 Compose 服务 | 至少注册飞书每日同步、备份、过期导出清理等已确认业务定时任务，并部署 worker/beat，具备重试、幂等和失败记录 | Celery 仅注册示例 `tasks.sample_add`；无业务任务、beat schedule、worker/beat 容器或运行证据 | 待分配 | — | 任务注册契约 + eager 模式业务测试 + worker/beat 容器冒烟 + 重试/幂等测试 | OPEN | 正式上线评审前 |
| PILOT-007 | 正式上线准备 / 故障告警 | P1 | 在应用、迁移和测试中搜索备份失败、飞书同步失败、回调连续失败的告警发送、告警记录和恢复闭环 | 故障触发脱敏告警并到达指定联系人，系统保留发生、通知、处理和恢复记录 | 无故障告警 Provider/Service/Model/Task 和发送测试；现有前端 `Alert` 组件只用于页面提示，不是运维告警 | 待分配 | — | 告警 Provider 单测 + 脱敏测试 + 连续失败阈值测试 + 沙箱消息送达演练 | OPEN | 正式上线评审前 |
| PILOT-008 | 自动化质量 / 核心资产维护 | P1 | 在 `back/` 执行 `.venv/bin/python -m pytest tests --ignore=tests/test_environment_contract.py --cov=app --cov-report=term-missing -q` | 核心资产更新、主附关系、公共使用对象、调拨、维修和报废均有正常/异常/权限/并发/审计回归，关键 Service 的未覆盖分支经风险评审 | 当前工作区新增 22 条定向用例，完整业务回归 `696 passed`，总覆盖率 89%；`asset_management_service.py` 由 29% 提升至 85%，API 由 78% 提升至 89%；待独立复验 | 待分配 | 当前未提交工作区 | `back/tests/test_asset_management_service.py` + 全量业务覆盖率回归 | READY_FOR_RETEST | 核心业务人工验收前 |
| PILOT-009 | 核心业务 / 调拨报废审批 | P1 | 使用有权限账号调用 `/api/v1/asset-actions/transfer` 或 `/api/v1/asset-actions/scrap`，随后检查资产、履历和 `operation_requests` | 调拨创建一层内部审批申请、报废创建两层顺序审批申请；审批完成前资产不变且有业务锁，最终通过后才执行 | 两个 Blueprint 直接调用 `asset_management_service.transfer()` / `scrap()` 并提交资产变更；未创建审批申请、审批任务或审批人快照，申请人自审限制也未生效 | 待分配 | — | API 提交不变更测试 + 审批层级/自审/锁测试 + 最终通过执行测试 + 拒绝/撤回释放锁测试 | OPEN | 核心业务人工验收前 |
| PILOT-010 | 核心业务 / 金额校验 | P1 | 直接提交负的预计/实际维修金额，或提交负数/缺失的报废回收金额 | 维修金额可空但不能小于 0；报废回收金额必填、允许 `0.00`、不能小于 0 | 修复前后端 Schema 接受上述非法输入；当前工作区已增加非负校验、报废金额必填约束和前端必填提示，定向回归通过 | 待分配 | 当前未提交工作区 | `test_lifecycle_schemas_reject_negative_amounts` + `test_scrap_schema_requires_recovery_amount` + 前端类型/Lint/表单复验 | READY_FOR_RETEST | 核心业务人工验收前 |
| PILOT-011 | 基础资料 / 公共使用对象 | P2 | 创建第一个公共使用对象并尝试以全空白名称创建或更新 | 编码使用 `PUB` + 至少 6 位流水号；服务层拒绝空白名称 | 修复前生成 `PUB0001` 且空白名称可绕过 Schema 写入；当前工作区改为 `PUB000001` 并在创建/更新服务层拒绝空白名称 | 待分配 | 当前未提交工作区 | `test_public_object_code_uses_six_digit_sequence` + 创建/更新空白名称测试 + HTTP 边界测试 | READY_FOR_RETEST | 基础资料人工验收前 |

## 字段约束

- 严重级别：`P0`、`P1`、`P2`、`P3`。
- 状态：`OPEN`、`FIXING`、`READY_FOR_RETEST`、`VERIFIED`、`RISK_ACCEPTED`。
- `RISK_ACCEPTED` 禁止用于 P0/P1；P2 风险接受必须记录临时措施、批准人和明确期限。
- 修复缺陷前先增加能复现问题的自动化回归用例；无法自动化时，在“回归用例”中写明可重复的人工步骤和证据位置。

## 严重级别

- P0：凭据泄漏、越权访问、误连正式环境、不可恢复的数据破坏或安全日志泄密；立即停止并隔离。
- P1：登录或核心流程不可用、资产状态/金额错误、附件丢失、迁移失败或备份无法恢复；阻断下一阶段。
- P2：非核心异常、明显性能下降、提示不清或兼容性问题；原则上试运行前修复。
- P3：轻微样式、文案、间距、Logo 尺寸或非关键交互问题；纳入有期限的整改清单。
