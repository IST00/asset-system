# 资产系统后端基础架构设计

## 1. 目标

第一阶段在现有 Flask 脚手架上建立可长期扩展的后端基础架构，并完成一条真实、可运行的资产入库业务纵切。

本阶段不是只创建空目录，也不一次铺开全部资产业务。实现范围为：

- 可运行的用户、角色、权限和数据范围基础能力；
- 公司组织、资产分类、计量单位、资产来源和地点基础资料；
- 资产编码生成与永久占用；
- 单件及多件资产入库申请；
- 一层内部入库审批；
- 审批通过后的正式资产入库；
- 资产列表、详情、履历和操作日志；
- 完整的迁移、测试、启动和真实 HTTP 验证。

第一阶段为后续审批、导入、主附资产、领用退库、转移、维修、报废、盘点、飞书和文件存储定义清晰边界，但不实现这些后续业务。

## 2. 设计原则

采用模块化分层单体。后端保持一个 Flask 应用和一个数据库，遵守仓库既有依赖方向：

```text
Blueprint / Schema -> Service -> Repository -> SQLAlchemy Model
```

具体原则如下：

1. Blueprint 只处理 HTTP 边界、Schema 校验、JWT 身份读取和 Service 调用。
2. Service 负责业务规则、跨模块编排和事务边界。
3. Repository 只负责本模块的数据访问，不提交事务、不判断权限、不抛业务异常。
4. SQLAlchemy Model 只表达持久化结构和本模型局部约束。
5. 跨模块协作调用对方 Service 的公开方法，不直接访问对方 Repository。
6. 同步数据库业务使用明确的直接调用，不引入事件总线、插件系统或反射注册。
7. 不创建万能 `BaseService`、通用审批 JSON 大表或无边界的 `utils` 集合。
8. 只为明确需要替换的外部能力建立适配接口，例如未来的文件存储、飞书客户端和通知渠道。

## 3. 模块划分

### 3.1 身份与权限

负责：

- 本地管理员登录和当前用户查询；
- 用户、角色、权限和用户角色关系；
- 角色权限聚合；
- 数据范围计算；
- 统一的功能权限和数据权限判断。

数据范围支持：

```text
ALL
DEPARTMENT
DEPARTMENT_TREE
SELF
CUSTOM
```

第一阶段实现可运行的数据范围模型和统一检查入口。超级管理员拥有全部权限；资产管理员拥有本阶段基础资料、资产和入库权限。自定义角色不需要修改业务代码即可生效。

用户拥有多个角色时，功能权限取并集。数据范围也取并集，其中 `ALL` 直接覆盖其它范围；`DEPARTMENT`、`DEPARTMENT_TREE`、`SELF` 和 `CUSTOM` 的可见数据合并计算。金额等字段权限仍需显式拥有对应权限，不能仅凭数据范围获得。

### 3.2 组织

负责公司编码、公司层级、顶级公司解析、启用和停用规则。

组织编码按字符串保存，全局唯一，创建后不可修改。资产编码使用资产所属组织对应的顶级公司编码。

### 3.3 资产分类与基础字典

负责：

- 资产分类编码、层级、默认使用期限和默认计量单位；
- 计量单位；
- 资产来源；
- 层级地点及地点是否允许存放资产。

分类编码创建后不可修改。被业务数据引用的基础资料不能删除，只能停用。本阶段不实现供应商和附件。

### 3.4 资产编码与资产台账

负责：

- 按“顶级公司编码 + 资产分类编码”维护独立流水；
- 生成至少四位、可自动扩位的资产编码；
- 记录编码的占用状态；
- 创建和查询正式资产；
- 保证资产编码及非空设备序列号唯一。

编码状态为：

```text
PENDING_STOCK_IN
ACTIVE
VOID
```

被拒绝、撤回或取消的入库申请所占编码变为 `VOID`，永久不复用。

### 3.5 入库申请

入库申请是首阶段的业务编排模块，负责协调：

```text
PermissionService
OrganizationService
AssetCategoryService
AssetCodeService
ApprovalService
AssetService
AuditService
```

入库模块保存入库特有的申请和明细，不把业务字段塞进通用申请表的 JSON 字段。

### 3.6 审批

审批模块只管理：

- 通用申请状态；
- 审批步骤和任务；
- 审批人及审批意见；
- 审批记录和审批状态变化。

审批模块不了解资产字段，也不直接创建资产。第一阶段只实现一层内部入库审批，但数据边界允许后续增加流程版本、多层、或签、会签和其它业务申请。

### 3.7 审计与资产履历

操作日志记录系统级业务操作；资产履历记录单件资产的生命周期变化。审计模块只记录已经发生的事实，不参与业务决策。

与正式资产变更相关的履历和操作日志必须与资产变更处于同一事务，避免资产成功但履历缺失。

## 4. 数据模型

第一阶段新增或调整以下模型：

### 4.1 权限

```text
users
roles
permissions
user_roles
role_permissions
role_data_scopes
role_data_scope_organizations
```

现有 `users.role` 单字符串只作为迁移来源。新迁移将已有角色回填到 RBAC 关系表并移除旧字段，业务代码不同时读取两套角色来源。

### 4.2 基础资料

```text
organizations
units
asset_sources
asset_locations
asset_categories
```

组织、分类和地点使用 `parent_id` 表达层级，并保存稳定编码。层级修改不改变稳定编码。

### 4.3 申请与审批

```text
operation_requests
stock_in_requests
stock_in_items
approval_steps
approval_tasks
approval_records
```

`operation_requests` 只保存申请编号、操作类型、申请人、审批状态、执行状态、流程版本和时间等流程共性。入库资产字段保存在 `stock_in_items`。

### 4.4 编码与资产

```text
asset_code_sequences
asset_code_reservations
assets
asset_lifecycle_records
operation_logs
```

编码流水以顶级公司编码和分类编码组成唯一键。编码占用记录以资产编码组成唯一键。正式资产表再次使用唯一约束防止重复编码。

## 5. 状态模型

审批状态：

```text
PENDING
APPROVED
REJECTED
WITHDRAWN
```

执行状态：

```text
NOT_STARTED
PROCESSING
SUCCESS
FAILED
TERMINATED
```

资产状态：

```text
IDLE
IN_USE
REPAIRING
SCRAPPED
```

审批结果和执行结果独立保存。审批已经通过但正式入库失败时，审批状态保持 `APPROVED`，执行状态改为 `FAILED`。

## 6. 入库业务流程

### 6.1 提交

```text
读取当前用户
-> 检查 stock-in:create 权限和组织数据范围
-> 校验组织、分类、单位、来源、地点和责任管理员
-> 校验全部入库明细
-> 锁定对应编码流水并逐件分配编码
-> 创建通用申请、入库申请、入库明细和编码占用记录
-> 创建第一层审批任务
-> 提交事务
```

只要任意一件资产校验失败，整个申请不创建，也不分配编码。

第一阶段一张入库申请中的资产必须属于同一个所属组织；跨组织资产拆成多张申请。提交时按照该组织筛选同时拥有 `stock-in:approve` 权限、数据范围覆盖该组织且账号有效的审批人，并把具体人员保存为审批人快照。没有符合条件审批人时禁止提交。

### 6.2 审批通过

审批和执行使用两个明确事务：

1. 第一个事务校验审批权限、申请状态和数据范围，并永久保存审批通过结果。
2. 第二个事务重新校验申请明细，整单创建正式资产、激活编码、写资产履历和操作日志。

第二个事务任意一步失败时整单回滚，再将执行状态可靠地记录为 `FAILED`。审批结果不回退。

新增资产入库是允许申请人自审的明确例外。申请人同时拥有 `stock-in:create`、`stock-in:approve` 且数据范围覆盖本申请组织时，可以审批自己提交的入库申请；否则不能调用审批接口。

### 6.3 拒绝与撤回

拒绝时审批人必须填写原因。撤回只允许申请人在审批完成前执行。拒绝或撤回后正式资产不发生变化，相关编码占用全部标记为 `VOID`。

### 6.4 重试

只有拥有 `approval:execution:retry` 权限且数据范围覆盖申请全部资产的用户可以重试。重试不能修改已审批内容，执行成功后重复重试直接返回当前成功结果，不重复创建资产和履历。

## 7. 第一阶段资产字段

入库申请和正式资产覆盖：

```text
所属公司
资产分类
资产名称
计量单位
采购金额
购入日期
资产责任管理员
资产来源
存放地点
规格型号
设备序列号
收货单号
备注
零金额原因
```

前九项为固定必填字段。零金额原因在采购金额为 `0.00` 时必填。采购金额使用 `DECIMAL(18,2)`，不得为负数；资产来源为采购且金额为零时，只要已填写原因即可提交，不引入额外确认接口。设备序列号允许为空，填写后忽略大小写和前后空格，在正式资产和未结束入库申请之间执行唯一校验。

本阶段不实现供应商、照片附件、主附资产、RFID、二维码文件、公共使用对象和扩展属性。

## 8. API 范围

所有接口使用 `/api/v1` 前缀，只使用 GET 和 POST。

### 8.1 身份与权限

```text
POST /api/v1/auth/login
GET  /api/v1/users/me
GET  /api/v1/users
GET  /api/v1/roles
GET  /api/v1/permissions
POST /api/v1/roles
POST /api/v1/roles/<id>/update
POST /api/v1/roles/<id>/permissions/update
POST /api/v1/users/<id>/roles/update
```

不保留面向未认证用户的公开注册接口。

### 8.2 基础资料

组织、分类、单位、来源和地点分别提供：

```text
GET  列表或树
GET  详情
POST 新增
POST /<id>/update
POST /<id>/disable
POST /<id>/enable
```

本阶段不提供已引用主数据的物理删除接口。

### 8.3 入库与资产

```text
POST /api/v1/stock-in-requests
GET  /api/v1/stock-in-requests
GET  /api/v1/stock-in-requests/<id>
POST /api/v1/stock-in-requests/<id>/approve
POST /api/v1/stock-in-requests/<id>/reject
POST /api/v1/stock-in-requests/<id>/withdraw
POST /api/v1/stock-in-requests/<id>/retry
GET  /api/v1/assets
GET  /api/v1/assets/<id>
GET  /api/v1/assets/<id>/lifecycle
GET  /api/v1/audit-logs
```

列表接口支持分页和必要筛选。第一页编号继续遵守现有脚手架的零基分页约定。

## 9. 权限策略

业务代码使用权限编码和数据范围，不使用散落的 `role == "ADMIN"` 判断。

第一阶段至少包含：

```text
system:user:view
system:role:view
system:role:manage
organization:view
organization:manage
asset-category:view
asset-category:manage
unit:view
unit:manage
asset-source:view
asset-source:manage
location:view
location:manage
asset:view
asset:amount:view
stock-in:create
stock-in:view
stock-in:approve
approval:execution:retry
audit:view
```

功能权限和数据权限都由后端执行。前端隐藏按钮只能改善体验，不能替代后端授权。

## 10. 代码边界与错误处理

- Marshmallow Schema 负责请求类型、长度、范围和格式校验。
- Service 接收普通参数或字典，不依赖 Flask `request`。
- Repository 不知道当前用户、JWT、HTTP 或业务权限。
- Service 返回字典或明确的结果对象，不把 Model 返回给 Blueprint。
- 业务失败抛 `BusinessException(ResultCode.X)`，Blueprint 不手写失败响应。
- 数据库唯一约束是并发安全的最后防线，业务层仍提供可理解的错误信息。
- 对外错误不暴露 SQL、密码、Token、密钥或服务器文件路径。
- 响应体遵守现有 `{code, message, data}`，请求关联标识使用现有 `X-Request-ID` 响应头和日志。

本阶段不修改 `Result`、`ResultCode`、全局错误处理器或 Flask 应用装配顺序，避免把普通业务开发与脚手架核心变更混在同一个分支。

## 11. 迁移策略

现有 `001_init.py` 不修改。所有模型和 RBAC 调整通过新的顺序 Alembic 迁移完成。

迁移需要支持：

- 从空数据库按顺序升级；
- 从现有 `001` 数据库升级；
- 将已有 `ADMIN` 和 `USER` 字符角色回填到 RBAC 关系；
- 为默认超级管理员建立新角色关系；
- 保证所有新增唯一约束、外键和必要索引存在。

正式资产、申请、审批、编码占用、履历和审计记录不提供物理删除迁移。

## 12. 测试与完成标准

### 12.1 自动化验证

必须通过：

```bash
cd back
ruff check .
ruff format --check .
mypy app/ config.py
pytest
```

测试至少覆盖：

- 登录、当前用户、角色权限聚合和数据范围；
- 组织、分类和字典的启停与引用限制；
- 资产必填、金额、日期和序列号规则；
- 并发编码分配和唯一约束；
- 拒绝、撤回后的编码作废；
- 无权限审批、符合条件的入库自审和重复审批；
- 多件资产整单成功或整单回滚；
- 审批成功、执行失败及安全重试；
- 资产列表的数据范围和金额字段权限；
- 履历和操作日志；
- 全新数据库及现有 `001` 数据库的迁移升级。

### 12.2 实际运行验证

启动真实 Flask 后端并通过 HTTP 完成：

```text
管理员登录
-> 创建基础资料
-> 配置角色权限
-> 提交入库申请
-> 审批
-> 查询正式资产
-> 查看履历与操作日志
```

同时检查健康接口和数据库迁移结果。MySQL 特有的行锁及并发行为需要在 Docker MySQL 环境验证，不能只依赖测试用 SQLite。

## 13. 独立审查闭环

主线程开发和自检完成后，启动一个独立审查代理。审查代理只读检查代码和运行验证命令，不得修改文件。

审查范围固定为：

1. 本设计范围内的需求完整性；
2. 逻辑正确性；
3. 边界情况；
4. 代码质量和模块耦合；
5. 测试覆盖；
6. 实际启动和 API 运行结果。

问题清单中的每项需要包含严重程度、证据、影响和建议验证方式。主线程负责修复，再将同一代码交回同一个审查代理复验。循环持续到全部通过；如受环境、外部依赖或需求冲突阻塞，必须明确记录阻塞条件、已经完成的验证和剩余风险。

## 14. 明确不做

第一阶段不实现：

- 通用审批流程配置页面；
- 多层、或签、会签、转交、催办和终止执行；
- 飞书登录、组织同步、审批和通知；
- Excel 导入导出；
- 主附资产；
- 领用、退库、转移、维修和报废；
- 盘点；
- 二维码、条形码和标签 PDF；
- 文件上传、附件和 MinIO；
- Redis 或 Celery 业务任务；
- 前端页面。

这些能力后续按同样的模块边界分别设计和实现，不通过向本阶段 Service 添加条件分支来拼接。
