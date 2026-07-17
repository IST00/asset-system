# 多功能并行开发业务操作底座设计

**状态：** 已批准，待用户书面复核

**需求来源：** [`docs/product/资产系统建设方案.md`](../../product/资产系统建设方案.md)，其中第 14 章确认记录优先于前文概括性建议。

**技术基线：** Python 3.13、Flask 3、SQLAlchemy 2、Alembic、MySQL 8、React 18；不使用 Redis。继续遵守 `api -> services -> repositories -> models` 分层和 GET/POST-only API 约定。

## 1. 目标

建设一个只面向资产系统的两层公共底座，使领用/退库、调拨、维修、报废等功能可以在独立 worktree 中并行开发，同时共享一致的审批、锁定、并发、执行、履历和审计语义。

底座完成后先迁移现有入库流程作为兼容性样板。入库接口和业务结果保持不变，通过后才冻结公共契约并开始多功能并行开发。

## 2. 非目标

- 不建设 BPMN 或通用低代码工作流平台。
- 不支持脚本节点、任意条件表达式、并行网关、定时自动审批或自由画流程图。
- 不把各功能的业务字段全部塞进通用 JSON；每个功能继续拥有显式模型和 Schema。
- 不在底座阶段实现飞书开放平台的全部接口；只冻结适配契约、状态和幂等存储，并提供本地模拟实现。
- 不把盘点任务强行改造成普通审批申请；盘点保留独立任务状态机。
- 不在本阶段开发领用、调拨、维修、报废、盘点或报表的完整业务页面与接口。

## 3. 核心原则

1. **申请与执行分离。** 审批结果不能因业务执行失败而回退。
2. **业务字段显式建模。** 公共底座管理生命周期，各功能管理自己的业务明细。
3. **整单原子性。** 一张申请中的全部资产统一通过、拒绝和执行，不支持部分批准。
4. **数据库最终防线。** 业务锁唯一约束、资产版本 CAS、审批终态 CAS 和回调事件唯一约束共同处理并发。
5. **提交时快照。** 资产关键信息、流程版本、审批人名单和角色解析结果提交后不可被配置变化覆盖。
6. **模块文件独占。** 功能 Agent 新增自己的文件，不直接修改公共聚合、迁移和注册文件；主线程负责集成。
7. **最小公共接口。** 只抽取至少两个业务功能真正共用的能力，不创建通用 CRUD 或插件框架。

## 4. 总体架构

```text
功能 API / Schema
    -> 功能 Service（业务规则、显式明细表）
        -> Operation Service（申请生命周期）
            -> Approval Engine / Approval Provider
            -> Asset Lock Service
            -> Operation Executor
                -> 功能 Operation Handler
                    -> Asset Transition Service
                    -> Lifecycle / Audit Service
        -> 显式 Repository
            -> SQLAlchemy Model / MySQL
```

公共底座分为两层：

- **业务操作内核：** 申请、资产清单、快照、业务锁、执行尝试、重试、终止、履历和审计。
- **审批内核：** 流程定义与版本、多层审批、或签/会签、审批人快照、自审策略，以及内部/飞书/直接确认三种通道。

## 5. 公共领域模型

### 5.1 现有资产聚合的公共字段

现有 `assets.organization_id` 继续表示资产所属公司/组织，是资产编码和财务归属依据。系统不新增“使用公司”。

底座为后续功能冻结以下公共含义：

```text
status                 IDLE / IN_USE / REPAIRING / SCRAPPED
organization_id        所属公司或组织，不随使用人变化
usage_type              PERSONAL / PUBLIC，可为空表示尚未投入使用
holder_user_id          个人使用员工，可为空
public_object_id        公共使用对象，可为空
usage_department_id     个人使用部门，可为空，跟随员工部门同步
location_id             当前实际存放地点
manager_id              资产责任管理员
parent_asset_id         单层主附关系中的主资产，可为空
version                 资产并发更新版本
```

约束：

- `PERSONAL` 在用资产必须有 `holder_user_id`，不得有 `public_object_id`。
- `PUBLIC` 在用资产必须有 `public_object_id` 和可选择的 `location_id`，不得有 `holder_user_id`。
- `IDLE` 资产不保留个人或公共使用对象。
- `SCRAPPED` 是业务终态，不能再领用、退库、调拨或维修。
- 员工部门同步只更新 `usage_department_id`，不得修改 `organization_id` 或资产编码。
- 主附关系只允许一层；同一批业务逐件锁定、校验、执行和写履历。

`usage_department_id` 继续引用当前 `organizations` 层级树中映射飞书部门的节点，避免再引入一套与 RBAC 数据范围不一致的部门树。

公共使用对象不伪装成可登录用户，新增 `public_usage_objects`：

```text
id
code                     PUB + 至少 6 位流水号，全局唯一且不可修改
name                     全局唯一
status                   ENABLED / DISABLED
created_at
updated_at
```

公共对象没有密码、JWT 或飞书身份；停用后不能用于新操作，历史资产和履历继续显示原对象。

### 5.2 通用申请

继续使用 `operation_requests`，补充以下字段：

```text
parent_request_id          被拒后重新提交时关联原申请
approval_channel           INTERNAL / FEISHU / DIRECT
approval_flow_version_id   内部审批使用的不可变流程版本，可为空
external_instance_id       飞书实例标识，可为空
submitted_at
approved_at
executed_at
terminated_at
terminated_by
termination_reason
```

审批状态继续使用：

```text
PENDING / APPROVED / REJECTED / WITHDRAWN
```

执行状态继续使用：

```text
NOT_STARTED / PROCESSING / SUCCESS / FAILED / TERMINATED
```

审批状态和执行状态只能由公共服务转换，功能模块不得直接赋值。

### 5.3 申请资产清单

新增 `operation_request_assets`：

```text
id
operation_request_id
asset_id
asset_code_snapshot
asset_name_snapshot
asset_status_snapshot
asset_version_snapshot
organization_id_snapshot
holder_snapshot
location_snapshot
before_data
target_data
created_at
```

约束：`(operation_request_id, asset_id)` 唯一。该表是不可变审批快照和历史展示依据，不替代各功能的显式明细表。

### 5.4 当前业务锁

新增 `asset_business_locks`：

```text
asset_id                 唯一
operation_request_id
operation_type
applicant_id
locked_at
```

锁表只表示当前锁，不承担历史记录。拒绝、撤回、执行成功或终止后删除；执行失败继续保留。申请快照和操作日志永久保留锁定历史。

多资产加锁时按照 `asset_id` 升序写入，减少数据库死锁。唯一约束冲突统一转换为“资产正在处理其它申请”的业务异常，并返回冲突资产编码和申请编号。

### 5.5 执行尝试

新增 `operation_execution_attempts`：

```text
id
operation_request_id
attempt_no
trigger_type             APPROVAL / RETRY
triggered_by
status                   PROCESSING / SUCCESS / FAILED
error_code
safe_error_message
started_at
finished_at
```

`(operation_request_id, attempt_no)` 唯一。数据库异常详情只写受控日志，不进入接口或业务表；业务表只保存脱敏错误码和提示。

## 6. 审批内核

### 6.1 流程定义与不可变版本

新增：

```text
approval_flow_definitions
approval_flow_versions
approval_flow_layers
approval_flow_assignee_rules
```

流程定义按 `operation_type` 管理草稿、发布和停用。每次发布生成不可变版本；已提交申请保存版本 ID，不受后续配置修改影响。

每层字段至少包括：

```text
level_no
sign_mode                OR_SIGN / AND_SIGN
allow_self_approval
```

审批人规则支持：

```text
USER                     指定用户
ROLE                     按角色和数据范围解析用户
```

提交时解析所有层的实际审批人并保存运行时任务。任一层没有有效审批人时禁止提交。

### 6.2 运行时步骤与任务

复用并扩展现有 `approval_steps`、`approval_tasks`、`approval_records`：

- 提交时一次性创建所有层和审批人快照。
- 第一层为 `PENDING`，后续层为 `WAITING`。
- `OR_SIGN` 第一位同意者用 CAS 取得层终态，其余待办转为 `WITHDRAWN`。
- `AND_SIGN` 必须全部同意；任一拒绝立即拒绝整张申请。
- 当前层通过后才激活下一层。
- 最后一层通过后，将申请审批状态 CAS 为 `APPROVED`，再触发业务执行。
- 每一步决定、转交和状态变更永久保存，不覆盖旧记录。

申请人自审同时受流程层配置和功能固定规则约束。正式环境的调拨、报废等禁止自审；入库和公共资产直接确认按建设方案允许自审。

### 6.3 审批通道

```text
INTERNAL   使用资产系统内部审批引擎
FEISHU     使用飞书实例，资产系统同步状态
DIRECT     不创建审批任务，由有权限人员直接确认后执行
```

定义窄接口：

```python
class ApprovalProvider(Protocol):
    def submit(self, operation_request_id: int) -> str | None: ...
    def withdraw(self, operation_request_id: int, actor_id: int) -> None: ...
    def urge(self, operation_request_id: int, actor_id: int) -> None: ...
```

内部审批不通过该接口绕回自身。飞书实现返回外部实例 ID；本地开发使用确定性的模拟 Provider。回调处理使用独立的外部事件 ID 唯一约束，同一事件重复投递只能生效一次。

底座只冻结 Provider 和幂等模型；真实飞书 API、签名验证、消息卡片和回调接入作为单独功能开发。

## 7. 功能 Handler 契约

每种会修改资产的操作提供一个 Handler：

```python
class OperationHandler(Protocol):
    operation_type: str

    def revalidate_for_execution(self, operation_request_id: int) -> None: ...
    def execute(self, operation_request_id: int, actor_id: int) -> None: ...
```

功能 Service 负责提交阶段：

1. 校验功能权限、数据范围和请求字段。
2. 一次性加载并逐件校验资产。
3. 调用公共服务按 ID 升序取得业务锁。
4. 再次校验资产状态和版本。
5. 创建通用申请、资产快照和自己的显式明细。
6. 根据操作类型启动内部审批、飞书审批或直接确认。
7. 在同一事务提交申请和锁。

公共 Executor 负责执行阶段：

1. 使用 `(operation_type -> handler)` 显式注册表找到 Handler。
2. 新建执行尝试记录。
3. Handler 重新校验不可变申请和当前资产状态。
4. Handler 在一个事务中更新全部资产。
5. 每件资产使用 `WHERE id = ? AND version = ?` CAS 更新。
6. 每件资产写生命周期记录，整单写操作日志。
7. 成功后释放业务锁；失败时回滚资产变更、保留锁并记录脱敏失败结果。

Handler 注册表由主线程维护。功能 Agent 只提供 Handler 类，不直接修改公共注册文件。

## 8. 状态转换边界

| 功能 | 允许的起始状态 | 成功后的状态或变化 |
| --- | --- | --- |
| 入库 | 无正式资产 | 新建 `IDLE` |
| 个人领用 | `IDLE` | `IN_USE`，设置员工和使用部门 |
| 公共投入使用 | `IDLE` | `IN_USE`，设置公共对象和地点 |
| 个人退库 | `IN_USE` 且属于申请人 | `IDLE`，清空使用对象并设置退库地点 |
| 公共退回闲置 | `IN_USE` 且为公共使用 | `IDLE`，清空公共对象并设置地点 |
| 调拨 | `IDLE` 或 `IN_USE` | 状态不变，更新使用对象、使用部门和地点 |
| 开始维修 | `IDLE` 或 `IN_USE` | `REPAIRING`，明细保存维修前状态 |
| 完成维修 | `REPAIRING` | 每件资产恢复自己的维修前状态 |
| 报废 | 非 `SCRAPPED` | `SCRAPPED`，写报废日期和回收金额 |
| 盘点提交 | 任意非报废或任务快照状态 | 不直接修改台账状态 |
| 盘点异常处理 | 按异常处理规则 | 通过独立申请调用操作内核更新明确字段 |

具体功能可以缩小允许状态，但不得绕过 `SCRAPPED` 终态和资产 CAS。

## 9. 各功能与审批方式映射

| 功能 | 通道 | 默认流程 |
| --- | --- | --- |
| 入库 | `INTERNAL` | 所属公司资产管理员一层或签；具备权限时允许自审 |
| 个人领用 | `FEISHU` | 资产管理员发放，员工确认收到；默认无部门负责人审批 |
| 公共投入使用 | `DIRECT` | 有权限管理员直接确认，允许自审 |
| 个人退库 | `FEISHU` + 系统验收 | 员工发起，管理员验收并填写退库地点 |
| 公共退回闲置 | `DIRECT` | 有权限管理员直接确认，允许自审 |
| 调拨 | `INTERNAL` | 资产管理员一层或签，正式环境禁止自审 |
| 维修 | `DIRECT` | 管理员直接开始，管理员确认完成，允许同一人 |
| 报废 | `INTERNAL` | 第一层资产管理员、第二层财务；禁止申请人自审 |
| 盘点 | 独立任务状态机 | 正常结果自动确认；异常处理完成后才可调用操作内核 |
| 报表 | 无 | 只读查询，不进入操作内核 |

## 10. 拒绝、撤回、重试和终止

- 拒绝：必须有原因；不修改正式资产；释放锁；原申请不可编辑。重新提交创建新申请并关联原申请。
- 撤回：只允许申请人在审批完成前操作；飞书通道由回调同步；释放锁；重复通知幂等。
- 执行失败：审批保持通过，资产事务全部回滚，业务锁保留。
- 重试：仅有权限人员操作；使用原快照和原明细；每次形成执行尝试记录。
- 终止：只允许执行失败申请；必须填写原因并二次确认；不修改资产，释放锁，执行状态变为 `TERMINATED`。

## 11. 并发和幂等

- 同一资产只能存在一条当前业务锁，数据库唯一索引是最终防线。
- 申请、步骤、任务和资产状态转换使用版本号或状态条件 CAS。
- 多资产按 ID 排序锁定和更新，降低 MySQL 死锁概率。
- 提交、审批、重试和回调都接受幂等键；同一用户操作重复请求返回已有结果，不产生第二张申请或第二条终态记录。
- 飞书回调事件 ID 唯一；状态只能按允许方向推进，旧事件不得覆盖新状态。
- 执行成功后重复执行返回原成功结果，不重复写资产履历。

## 12. API 和错误边界

- 功能 API 继续使用独立路径，例如 `/api/v1/asset-use-requests`。
- 公共审批 API 只处理内部审批任务、重试、终止和通用申请查询。
- 飞书回调使用独立、可验证签名的集成路径。
- 所有失败通过 `BusinessException` 映射统一响应；不得返回 SQL、凭据、外部响应正文或堆栈。
- Blueprint 只做 Schema 校验、JWT 边界和 Service 调用，不访问 Model 或 DB。
- 所有查询按权限和数据范围在 SQL 中过滤，不允许加载后再过滤。

## 13. 现有入库迁移

底座完成后，用现有入库作为第一个 Handler：

1. 为当前行为补充 characterization tests，锁定 API、编码、审批、执行失败和权限语义。
2. 将单层审批运行时迁移到新流程版本、步骤和任务模型。
3. 入库没有既有正式资产，不使用 `asset_business_locks`；资产编码占用继续由编码 reservation 管理。
4. 入库执行改由公共 Executor 调用 StockIn Handler。
5. 保持现有 `/api/v1/stock-in-requests` 合同和数据库历史可读。
6. SQLite upgrade/downgrade、MySQL 迁移和完整 HTTP 入库闭环全部通过后，才冻结底座接口。

## 14. 多 Agent 并行边界

### 14.1 主线程独占文件

主线程负责：

- 公共枚举、操作内核、审批内核和 Handler 注册表。
- `app/api/__init__.py`、各层 `__init__.py` 聚合导出。
- Alembic 迁移文件和多功能合并迁移。
- 公共权限种子、全量测试、运行验证和冲突处理。

功能 Agent 不得修改这些文件，只在交付清单中说明需要主线程注册的对象。

### 14.2 功能 Agent 独占文件

每个功能拥有独立的：

```text
models/<feature>.py
repositories/<feature>_repository.py
services/<feature>_service.py
services/<feature>_handler.py
schemas/<feature>.py
api/<feature>.py
tests/test_<feature>_*.py
```

并行 Agent 在独立 Git worktree 中开发。主线程先提交底座稳定基线，再创建所有 worktree。功能 Agent 不得直接合并或改写其它 Agent 的分支。

### 14.3 迁移所有权

功能 Agent 只提交模型和迁移需求说明，不创建或修改 Alembic 文件。主线程合并一批功能模型后，从统一 metadata 生成一份追加迁移，人工检查外键、索引、MySQL 兼容和 downgrade 数据语义。

这样避免多个分支产生相同 revision、多个 head 或迁移顺序冲突。

### 14.4 并行批次

底座和入库迁移完成前不启动功能 Agent。

第一批最多三个并行功能：

1. 领用与退库。
2. 调拨。
3. 维修。

第二批：

1. 报废。
2. 盘点，先单独拆成任务生命周期、扫码提交、异常复核和最终报告四个子规格。
3. 报表，先实现基于已完成数据的只读统计，再补跨功能指标。

## 15. 测试策略

### 15.1 公共契约测试

- 多层顺序审批。
- OR_SIGN 首人通过和其它任务结束。
- AND_SIGN 全员通过、任一拒绝。
- 申请人自审开关。
- 角色审批人和数据范围快照。
- 多资产整单校验、锁定、执行和回滚。
- 并发提交同一资产只能一张成功。
- 并发审批只能产生一个合法终态。
- 执行失败保留审批和锁，重试成功后只执行一次。
- 终止释放锁但不修改资产。
- 重复飞书回调和重复 HTTP 幂等键只生效一次。

### 15.2 功能契约测试

每个功能必须覆盖：权限、数据范围、允许状态、禁止状态、主附关系、批量原子性、字段快照、审批映射、成功履历、拒绝/撤回无资产变更、执行失败和幂等重试。

### 15.3 集成和运行验证

- Ruff、格式、mypy、pytest 全部通过。
- SQLite 迁移 upgrade/downgrade。
- MySQL 8 迁移、业务锁和并发 CAS。
- 真实 Flask 进程的健康检查、登录、提交、审批、执行和查询。
- 入库旧 API 的完整兼容性回归。
- 开发完成后由独立只读审查线程从需求完整性、逻辑正确性、边界情况、代码质量、测试覆盖和实际运行六方面审查；主线程修复后交回同一线程复验至通过或明确外部阻塞。

## 16. 验收标准

底座只有同时满足以下条件才可以作为并行开发基线：

1. 现有 63 个后端测试继续通过，新增公共契约测试全部通过。
2. 入库 API、审批、编码占用、执行失败和资产结果无行为回归。
3. 内部多层审批、或签、会签和流程版本可运行。
4. 同一资产并发申请只有一个成功，失败方收到确定性业务错误。
5. 多资产执行要么全部成功，要么全部回滚。
6. 失败重试和终止符合锁定规则，且无重复履历。
7. 本地模拟飞书 Provider 可驱动领用/退库的提交、确认、拒绝和撤回状态。
8. SQLite 和 MySQL 迁移均通过；如果环境阻止 MySQL 验证，必须明确记录残余风险。
9. 独立六维审查最终结论为 PASS。
10. 公共接口和主线程独占文件清单冻结并写入并行 Agent 任务说明。
