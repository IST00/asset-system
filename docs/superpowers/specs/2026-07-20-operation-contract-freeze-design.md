# 业务功能并行开发公共契约冻结设计

**日期：** 2026-07-20
**基线：** `feature/backend-foundation-v2` (`995922d`)
**需求来源：** `docs/product/资产系统建设方案.md` 与已批准的 `2026-07-17-operation-foundation-design.md`

## 1. 目标

在领用/退库、调拨、维修三个功能分支并行开发前，补齐并冻结它们必然共享的最小契约。完成后，功能分支只新增自己的领域文件，不再修改公共操作内核、资产并发更新、审计、注册或迁移文件。

本阶段只建设并行开发所需的公共能力，不实现任何一个完整业务功能。

## 2. 非目标

- 不实现领用、退库、调拨、维修、报废或盘点接口。
- 不接入真实飞书；继续使用现有 Provider 协议和本地模拟实现。
- 不实现短期借用、借期、逾期或续借。当前产品定义的是领用与退库。
- 不建设供应商、附件、照片或文件存储。
- 不增加 Redis，也不增加 Redis 配置或健康检查。
- 不允许功能分支各自扩展公共枚举、公共服务或 Alembic revision。

## 3. 总体方案

公共契约冻结分为六块：

1. 操作类型和审批后执行模式。
2. 申请创建、幂等重放和逐资产目标快照。
3. 资产批量锁行与版本 CAS 更新。
4. 通用资产履历和整单审计。
5. 主资产与直接附属资产展开。
6. 并行分支文件所有权、注册和迁移合并规则。

公共服务只提供机制。资产状态是否合法、目标使用人是谁、维修如何恢复等业务规则仍由各功能 Service 和 Handler 负责。

## 4. 操作类型与审批后执行

### 4.1 操作类型

`OperationType` 在开功能分支前一次性增加：

- `PERSONAL_USE`
- `PUBLIC_USE`
- `PERSONAL_RETURN`
- `PUBLIC_RETURN`
- `TRANSFER`
- `REPAIR_START`
- `REPAIR_COMPLETE`

`STOCK_IN` 保持不变。枚举值继续以字符串持久化，不使用数据库原生 Enum。

### 4.2 审批后执行模式

`OperationRequest` 新增非空字段 `approval_execution_mode`：

- `AUTO_ON_APPROVAL`：审批通过后立即调用公共 Executor。
- `MANUAL_CONFIRM`：审批通过后保持 `execution_status=NOT_STARTED`，保留业务锁，等待功能 Service 补齐验收信息后显式触发执行。

已有数据和未显式传值的申请默认 `AUTO_ON_APPROVAL`，保证入库和现有内部审批行为不变。

个人退库使用 `MANUAL_CONFIRM`。飞书批准只表示员工侧流程完成，管理员验收并填写退库地点后，功能 Service 才能触发执行。

内部审批最终通过、飞书回调通过和直接确认都必须进入同一个“审批完成后是否执行”公共判断，不得在各入口分别复制模式分支。`DIRECT` 申请本批只允许 `AUTO_ON_APPROVAL`；需要人工补充业务信息的流程使用审批通道加 `MANUAL_CONFIRM`，再由功能 Service 确认。

### 4.3 执行触发类型

`ExecutionTriggerType` 增加 `CONFIRMATION`。Executor 的合法组合为：

| 触发类型 | 执行模式 | 前置状态 |
| --- | --- | --- |
| `APPROVAL` | `AUTO_ON_APPROVAL` | 审批通过、未开始执行 |
| `CONFIRMATION` | `MANUAL_CONFIRM` | 审批通过、未开始执行 |
| `RETRY` | 任一模式 | 上次执行失败 |

非法组合抛 `BusinessException(ResultCode.BAD_REQUEST)`，不创建执行尝试。

审批拒绝、审批前撤回、执行成功和终止继续释放锁。审批通过但等待人工确认、执行失败继续保留锁。

## 5. 申请创建契约

### 5.1 幂等返回值

`operation_service.create_request()` 返回不可变结果对象：

```python
@dataclass(frozen=True)
class CreateOperationResult:
    operation: OperationRequest
    created: bool
```

首次创建返回 `created=True`；幂等键重放和唯一约束竞争后取回已有申请均返回 `created=False`。功能 Service 只有在 `created=True` 时才创建自己的申请明细，防止重复请求追加第二份明细。

### 5.2 目标快照

`create_request()` 接受 `target_data_by_asset_id: Mapping[int, Mapping[str, Any]]`。所有申请资产必须有且只有一份目标快照；缺失资产、多余资产或不可 JSON 序列化输入在写库前拒绝。

公共层继续生成 `before_data`，功能层只提供业务目标。例如调拨写目标使用人、部门和地点；维修开始写目标状态，维修前状态保存在功能明细和公共 `before_data` 中。

退库提交时尚未确定的验收地点不伪造进 `target_data`，由退库明细在管理员验收时保存；执行前 Handler 同时读取不可变提交快照和已确认的功能明细。

### 5.3 多组织资产

公共层取消“所有资产必须属于一个组织”的隐式限制，但不接管数据权限判断。功能 Service 必须在 SQL 查询阶段按当前用户数据范围加载全部资产，并把已验证的资产交给公共层。

公共层仍校验：资产已持久化、ID 不重复、按 ID 升序、目标快照集合完全匹配。功能 Service 负责决定某项业务是否允许跨组织；调拨的主附资产展开必须验证申请人同时拥有每件资产的数据权限。

## 6. 资产并发更新契约

`AssetRepository` 增加两个公共原语：

```python
def find_many_for_update(self, asset_ids: Sequence[int]) -> list[Asset]: ...

def cas_update(
    self,
    asset_id: int,
    expected_version: int,
    changes: Mapping[str, object],
) -> bool: ...
```

约束：

- `find_many_for_update` 对去重后的 ID 升序查询并加行锁；缺失资产由调用方统一报错。
- `cas_update` 使用 `WHERE id=:id AND version=:expected_version`，成功时原子执行 `version=version+1`。
- 本批可更新字段只允许 `status`、`usage_type`、`holder_user_id`、`public_object_id`、`usage_department_id` 和 `location_id`。
- 资产编码、所属公司、分类、采购金额和创建来源不得通过此接口修改。
- 返回 `False` 时 Handler 抛统一业务异常，使整单事务回滚；不得部分成功。

业务锁负责阻止并行申请，行锁与 CAS 负责防止执行时的并发覆盖，两者不能互相替代。

## 7. 通用履历与审计

`audit_service` 增加两个公共接口：

```python
def record_asset_lifecycle(
    *, asset_id: int, operation_type: str, request_no: str,
    actor_id: int, before_data: Mapping[str, Any],
    after_data: Mapping[str, Any],
) -> None: ...

def record_operation(
    *, operation_request_id: int, operation_type: str,
    actor_id: int, before_data: Mapping[str, Any] | None,
    after_data: Mapping[str, Any] | None,
) -> None: ...
```

每件被修改资产写一条 `AssetLifecycleRecord`，每张申请成功执行只写一条以 `operation_request` 为资源的 `OperationLog`。两者与资产更新处于同一事务，任一失败时整单回滚。

现有 `record_asset_stock_in()` 保留为兼容包装，不改变入库历史数据和现有测试合同。

## 8. 主附资产公共查询

公共关系服务只支持一层主附关系：

- `find_direct_children(parent_ids)` 按资产 ID 稳定排序返回直接附属资产。
- `expand_with_direct_children(asset_ids)` 返回去重、按 ID 排序的主资产和直接附属资产。
- 如果某个附属资产仍有子资产，视为非法多层关系并拒绝业务申请。
- 展开服务不判断业务是否必须携带附属资产，也不修改关系。

调拨必须自动展开全部直接附属资产；维修是否带附属资产由申请人显式选择；领用/退库的具体携带规则在功能规格中确定。所有展开后的资产仍需逐件进行权限、状态、业务锁和 CAS 校验。

## 9. 事务与错误边界

一次功能申请的公共申请、功能明细、资产快照和业务锁必须在同一事务提交。公共 Service 不在中途提交；HTTP Blueprint 不管理事务。

Executor 保持整单原子语义：重新校验、资产 CAS、履历、审计、执行尝试和锁释放形成一个成功事务。失败时资产、履历和成功审计全部回滚，另起事务记录脱敏失败尝试并保留业务锁。

所有契约错误通过 `BusinessException` 进入统一响应；不得把 SQL、连接信息、外部 Provider 正文或堆栈返回给客户端。

## 10. 并行分支边界

公共契约冻结提交并通过独立审查后，从同一个提交创建：

1. `feature/asset-usage-return`
2. `feature/asset-transfer`
3. `feature/asset-repair`

每个功能分支只新增自己的：

```text
models/<feature>.py
repositories/<feature>_repository.py
services/<feature>_service.py
operations/<feature>_handler.py
schemas/<feature>.py
api/<feature>.py
tests/test_<feature>_*.py
```

功能分支不得修改：

- 公共枚举、操作/审批/资产/审计公共服务。
- `app/__init__.py`、`app/api/__init__.py` 和各层 `__init__.py`。
- Handler 注册表、权限种子、`tests/conftest.py`。
- 任何 Alembic migration。

功能分支在交付清单中声明待注册 Blueprint、Handler、权限和模型。分支测试通过直接导入功能模型注册 metadata，不依赖修改聚合导出。

## 11. 迁移与合并所有权

主线程独占所有迁移：

1. 公共契约冻结使用 `004_operation_contract_freeze.py`，只增加 `approval_execution_mode`，已有行回填 `AUTO_ON_APPROVAL`；upgrade 和 downgrade 均兼容 SQLite 与 MySQL。
2. 三个功能分支不创建 migration，避免并行 head 和 revision 冲突。
3. 三个功能模型合并后，主线程生成一份 `005_parallel_operation_features.py`，统一创建领用退库、调拨和维修表、索引、外键及流程/权限种子。
4. 主线程一次性注册模型、Blueprint、Handler 和权限，然后运行 upgrade/downgrade、全量测试及跨功能锁冲突测试。

不采用多个功能 migration 加 merge revision 的方案，避免与已批准的“迁移由主线程独占”规则矛盾。

## 12. 测试策略

公共契约冻结按 TDD 实现，至少覆盖：

- 新操作类型和已有 `STOCK_IN` 兼容。
- 首次申请与幂等重放的 `created` 标志，包括并发唯一约束竞争。
- 目标快照完整性和序列化校验。
- 多组织资产不被公共层误拒绝，功能数据权限仍必须逐件验证。
- `AUTO_ON_APPROVAL` 自动执行。
- `MANUAL_CONFIRM` 审批通过后不执行、不释放锁；确认后只执行一次并释放锁。
- 非法执行触发组合不产生执行尝试。
- 批量锁行顺序、CAS 成功、版本冲突和整单回滚。
- 每资产一条履历、每申请一条审计；失败时不留下成功记录。
- 一层主附展开、去重、稳定排序和多层关系拒绝。
- 入库 API、审批、执行、幂等和资产结果无回归。
- Alembic 003→004 upgrade、004→003 downgrade，以及干净数据库完整升级。

门禁继续使用 Ruff、format、mypy、全量 pytest、`git diff --check` 和 convention guard。完成后由独立 Agent 从需求完整性、逻辑正确性、边界情况、代码质量、测试覆盖和实际运行六个方面只读审查；主线程修复后交同一 Agent 复验，直到 PASS 或明确阻塞。

## 13. 验收标准

1. 领用退库、调拨、维修功能分支不再需要修改公共操作契约。
2. 个人退库可以在飞书批准后保持待验收和业务锁，确认后才执行。
3. 幂等重放不会重复创建功能明细。
4. 所有资产变更通过统一行锁、CAS、履历和审计接口完成。
5. 主附资产展开只有一个公共实现，跨组织资产逐件执行数据权限校验。
6. 入库和现有公共审批行为不变。
7. 仓库无 Redis 配置或运行依赖。
8. 全量门禁通过，独立六维审查最终 PASS。
