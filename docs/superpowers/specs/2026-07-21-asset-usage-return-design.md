# 资产领用与退库设计

日期：2026-07-21
状态：已完成对话设计确认，等待书面规格确认

## 1. 目标

在已经冻结的公共操作契约上实现第一版资产领用与退库，覆盖：

- 个人领用；
- 个人退库；
- 公共资产投入使用；
- 公共资产退回闲置；
- 主资产自动携带全部直接附属资产；
- 本地模拟飞书确认、拒绝和撤回；
- 逐件退库验收和损坏说明。

本功能复用公共申请、审批、业务锁、资产快照、CAS、整单事务、履历和审计能力，不建立第二套工作流。

## 2. 非目标

第一版明确不做真实飞书 OpenAPI、短期借用、照片附件、损坏后自动维修、多层主附资产或 Redis。MySQL 继续使用部署环境提供的外部配置，不由 Docker 启动。本功能不改变健康检查和环境配置。

## 3. 复用边界与模块划分

依赖方向保持：

```text
asset_usage_return blueprint
  -> asset_usage_service / asset_return_service
  -> feature repositories + common operation services
  -> feature models + common models
  -> db session

operation executor
  -> personal/public usage/return handlers
  -> asset repository CAS + audit service
```

- Blueprint：JWT、Marshmallow 输入校验和统一响应，只调用 Service。
- Usage Service：领用资格、目标使用对象、部门、地点、主附展开和申请创建。
- Return Service：退库资格、员工本人边界、验收资料和人工确认。
- Feature Repository：只封装本功能明细的查询和持久化。
- Operation Handler：执行前重验、逐件 CAS 更新、履历和整单审计。
- 公共操作内核：申请状态、审批通道、幂等、业务锁、执行尝试、事务提交和失败脱敏。

Blueprint 不导入 `app.models` 或 `db`，也不返回 SQLAlchemy model。

## 4. 操作类型与审批模式

| 业务 | operation_type | approval_channel | execution_mode |
| --- | --- | --- | --- |
| 个人领用 | `PERSONAL_USE` | `FEISHU` | `AUTO_ON_APPROVAL` |
| 公共投入 | `PUBLIC_USE` | `DIRECT` | `AUTO_ON_APPROVAL` |
| 个人退库 | `PERSONAL_RETURN` | `FEISHU` | `MANUAL_CONFIRM` |
| 公共退回 | `PUBLIC_RETURN` | `DIRECT` | `AUTO_ON_APPROVAL` |

个人退库的飞书批准只表示员工侧流程完成。批准后资产继续保持业务锁，管理员完成验收后才以 `CONFIRMATION` 触发执行。

公共投入和公共退回由有权限的管理员直接确认。创建申请、保存功能明细和调用直接确认属于一个 Service 用例；重复请求根据公共幂等键返回原申请，不重复执行。

## 5. 数据模型

### 5.1 AssetUsageRequest

一张领用申请对应一条领用明细：

| 字段 | 约束 | 用途 |
| --- | --- | --- |
| `id` | 主键 | 明细标识 |
| `operation_request_id` | 唯一、非空、外键 | 关联公共申请 |
| `target_user_id` | 可空、外键 | 个人领用员工 |
| `target_public_object_id` | 可空、外键 | 公共使用对象 |
| `usage_department_id` | 可空、外键 | 根据个人领用员工自动解析的部门 |
| `target_location_id` | 可空、外键 | 领用后的统一地点 |

字段组合由 `operation_type` 约束：

- `PERSONAL_USE`：必须有 `target_user_id` 和 `usage_department_id`，不得有 `target_public_object_id`。
- `PUBLIC_USE`：必须有 `target_public_object_id` 和 `target_location_id`，不得有 `target_user_id`；`usage_department_id` 为空。
- 个人领用地点可以省略；省略时每件资产保留原地点，但目标快照仍保存解析后的实际地点。

### 5.2 AssetReturnRequest

| 字段 | 约束 | 用途 |
| --- | --- | --- |
| `id` | 主键 | 明细标识 |
| `operation_request_id` | 唯一、非空、外键 | 关联公共申请 |
| `return_location_id` | 可空、外键 | 退库后的存放地点 |
| `confirmed_by` | 可空、外键 | 管理员验收人 |
| `confirmed_at` | 可空 | 验收时间 |

个人退库提交时三个验收字段为空，管理员确认时一次写入。公共退回在创建时写入地点和确认人，再直接执行。

### 5.3 AssetReturnItem

每个 `OperationRequestAsset` 对应一条退库验收明细：

| 字段 | 约束 | 用途 |
| --- | --- | --- |
| `id` | 主键 | 明细标识 |
| `operation_request_asset_id` | 唯一、非空、外键 | 对应申请中的一件资产 |
| `condition` | 可空 | `NORMAL` 或 `DAMAGED` |
| `condition_description` | 可空文本 | 损坏说明 |

`DAMAGED` 必须填写非空说明；`NORMAL` 不保存损坏说明。损坏只作为退库事实保留，不阻止解除员工责任，也不把资产直接改为 `REPAIRING`。

三个模型都使用现有 `TimestampMixin`，不提供物理删除接口。历史关联对象以后停用时，不能破坏已有申请展示。

## 6. 主附资产规则

调用公共 `expand_with_direct_children()`：

1. 选择主资产时自动包含全部直接附属资产。
2. 请求同时包含主资产和附属资产时去重，并按资产 ID 稳定排序。
3. 只选择仍挂接的附属资产时拒绝；需要单独处理必须先解除主附关系。
4. 展开后逐件校验数据权限、资产状态、使用对象、业务锁和版本。
5. 任意一件不合格时整单不创建；执行期任意一件重验或 CAS 失败时整单回滚。
6. 每件资产分别保存提交快照、目标快照、履历和版本。

领用和退库同步附属资产的使用人、公共使用对象、使用部门和地点。处于维修或报废状态的附属资产会使整单失败，不被静默跳过。

## 7. 四种业务流程

### 7.1 个人领用

```text
管理员提交 -> 展开并校验 IDLE -> 解析员工部门
-> 创建 FEISHU + AUTO_ON_APPROVAL 申请并锁定
-> 本地飞书确认 -> 执行期重验
-> 整单更新为 IN_USE + PERSONAL
-> 写入员工、部门、地点、履历和审计 -> 释放锁
```

员工拒绝或申请撤回时，资产保持原值并释放锁。拒绝原因永久保留；修改后使用新幂等键重新发起。

### 7.2 个人退库

```text
员工提交本人资产 -> 展开并校验 IN_USE + PERSONAL + 本人持有
-> 创建 FEISHU + MANUAL_CONFIRM 申请并锁定
-> 本地飞书批准 -> 保持待验收和锁定
-> 管理员填写地点和逐件状况 -> 触发 CONFIRMATION
-> 整单更新为 IDLE，清空使用类型、员工、部门和公共对象
-> 写入地点、履历和审计 -> 释放锁
```

提交时尚未确定的退库地点不伪造进公共 `target_data`。目标快照只保存当时已确定的清空字段；Handler 在执行前同时读取不可变提交快照和已确认的退库明细。

### 7.3 公共投入

```text
管理员选择公共对象和地点 -> 校验资产 IDLE
-> 创建 DIRECT + AUTO_ON_APPROVAL 申请和完整目标快照
-> 系统内直接确认 -> 整单更新为 IN_USE + PUBLIC
-> 写入公共对象和地点，清空个人员工与部门
-> 写履历和审计 -> 释放锁
```

提交人与确认人允许是同一管理员。

### 7.4 公共退回

```text
管理员提交地点和逐件状况 -> 校验 IN_USE + PUBLIC
-> 创建 DIRECT + AUTO_ON_APPROVAL 申请和验收明细
-> 系统内直接确认 -> 整单更新为 IDLE
-> 清空使用类型、公共对象、员工和部门，写入地点
-> 写履历和审计 -> 释放锁
```

## 8. API

```text
POST /api/v1/asset-usage-requests/personal
POST /api/v1/asset-usage-requests/public
GET  /api/v1/asset-usage-requests
GET  /api/v1/asset-usage-requests/{operation_request_id}

POST /api/v1/asset-return-requests/personal
POST /api/v1/asset-return-requests/public
POST /api/v1/asset-return-requests/{operation_request_id}/confirm
GET  /api/v1/asset-return-requests
GET  /api/v1/asset-return-requests/{operation_request_id}
```

创建请求都包含 `asset_ids` 和可选 `idempotency_key`。个人领用额外包含员工和可选地点；公共投入包含公共对象和地点；公共退回包含地点和逐件验收数据；个人退库不能由请求体指定其他员工。

管理员确认个人退库必须提交地点、与申请资产完全一致的验收明细及可选动作幂等键。列表沿用 `page`/`size`，详情返回公共状态、资产快照、功能明细和允许动作。Schema 只输出 dict。

### 8.1 本地模拟飞书

开发和测试 Profile 提供：

```text
POST /api/v1/asset-usage-requests/{id}/mock-feishu-action
POST /api/v1/asset-return-requests/{id}/mock-feishu-action
```

动作只允许 `APPROVE`、`REJECT`、`WITHDRAW`，拒绝必须有原因，每个事件必须有幂等键。入口复用 `approval_provider_service.handle_callback()`，不得直接修改状态。生产 Profile 不注册对应路由；真实飞书以后只替换事件入口。

## 9. 权限和数据范围

- `asset:usage:manage`：个人领用、公共投入、公共退回、个人退库验收及权限范围内查询。
- `asset:return:self`：员工查看本人申请，并为自己名下资产创建个人退库。

所有展开资产都在 Service 逐件校验数据范围。员工个人退库还必须满足 JWT 用户等于 `holder_user_id` 且资产为个人在用。申请人、审批参与人和覆盖资产数据范围的管理员可以查看详情。模拟飞书入口不绕过 JWT 或参与人校验。

权限种子和聚合注册在三个并行功能合并阶段统一加入，功能分支不修改公共权限种子。

## 10. 校验和错误处理

提交期校验资产存在性和重复、主附关系、权限、用户/部门/公共对象/地点启用状态、地点可存放、资产业务状态和业务锁。执行期重新按 ID 升序锁定资产，重验提交版本和业务条件，再 CAS 更新；不相信创建时结果。

所有可预期失败抛 `BusinessException(ResultCode.X)`。数据库错误、SQL、连接信息、回调正文和堆栈不返回客户端。Executor 失败时回滚资产、履历和成功审计，记录脱敏失败尝试并保留业务锁，供重试或终止。

## 11. 幂等、事务和并发

- 创建申请沿用 `(applicant_id, operation_type, idempotency_key)` 唯一语义。
- 管理员退库确认使用公共动作幂等记录。
- 模拟飞书事件使用 Provider 事件唯一键。
- 已成功申请收到重复确认时不重复更新或写履历。
- 申请、功能明细、快照和业务锁在同一事务创建。
- 全部 CAS、履历、审计、执行尝试和锁释放属于同一成功事务。
- 不允许部分领用、部分退库或跳过失败资产。

## 12. 审计、查询与历史

每件成功资产写生命周期记录，包含前后状态、使用对象、部门、地点及退库状况；每张申请写一条整单操作日志。拒绝、撤回和失败不伪造成功履历。

列表和详情由 Feature Service 组装稳定 dict，包含申请状态、申请人、时间、目标、资产快照、验收状况和允许动作。历史名称优先使用快照；当前关联对象停用或改名不破坏历史。金额继续受公共字段权限保护。

## 13. 测试策略

按 TDD 覆盖：

1. 三个模型的约束和关联。
2. 个人领用提交、确认、拒绝、撤回和重复回调。
3. 个人退库本人边界、批准后待验收、逐件验收和重复确认。
4. 公共投入、公共退回的直接确认和幂等。
5. 主附展开、重复输入、单独附属资产、多层非法关系和跨范围拒绝。
6. 状态不符、停用对象、非法地点和业务锁冲突。
7. 版本变化、CAS 失败、履历失败和整单回滚。
8. 损坏说明必填、损坏不阻止退库、正常验收不保留损坏说明。
9. Schema、JWT、权限、分页、详情可见性和统一错误响应。
10. 模拟飞书路由只在允许 Profile 注册且事件幂等。

功能分支必须通过 Ruff、format、mypy 和全量 pytest。

## 14. 并行开发和合并边界

功能分支只新增本功能的 leaf model、repository、schema、service、handler、blueprint 和测试，不修改公共枚举、公共操作内核、聚合 `__init__.py`、注册文件、权限种子或 Alembic migration。

三个并行功能合并后，由主线程统一注册模型、Blueprint、Service 和 Handler，加入权限种子，生成 `005_parallel_operation_features.py`，验证 SQLite 升降级和 MySQL 兼容性，并运行全量门禁和实际 API 流程。

## 15. 完成标准

- 四种流程均可通过 API 完成并得到正确资产状态。
- 个人领用和退库可由本地模拟飞书驱动。
- 主附资产整单执行，无越权、部分成功或重复履历。
- 个人退库批准后保持待验收，验收确认只执行一次。
- 损坏资产正常解除责任并保留状况说明。
- 功能分支及合并后的 lint、类型检查、测试和迁移验证通过。
- 独立审查线程从需求完整性、逻辑正确性、边界情况、代码质量、测试覆盖和实际运行结果六方面给出 PASS。
