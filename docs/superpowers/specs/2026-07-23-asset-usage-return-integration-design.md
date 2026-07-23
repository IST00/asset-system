# 资产领用与退库集成设计

日期：2026-07-23
状态：基于已批准的领用/退库设计进入集成

## 1. 目标与边界

本阶段只把已经完成并通过六维审查的领用/退库 leaf 模块接入应用：

- 聚合导出 3 个模型；
- 注册领用、退库 Blueprint，并仅在开发/测试应用注册本地飞书 Blueprint；
- 注册 4 个操作处理器；
- 新增两项权限种子和默认角色授权；
- 新建不可变迁移 `005_asset_usage_return.py`；
- 验证迁移升降级、应用启动和现有四种业务流程。

本阶段不实现调拨、维修，不引入 Redis，不启动 Docker MySQL，也不修改健康检查。

## 2. 集成方式

### 2.1 模型与 API

`app.models` 导出 `AssetUsageRequest`、`AssetReturnRequest`、`AssetReturnItem`，确保 Flask-Migrate 和 `db.create_all()` 总能看到功能元数据。

领用与退库正式 Blueprint 在所有 Profile 注册。本地飞书路由只根据应用的 `TESTING` 或 `DEBUG` 状态注册；生产应用即使存在本地模拟开关也不暴露路由。Service 自身仍保留本地模式防线，形成“路由不可达 + Service 拒绝”的双层保护。

### 2.2 Handler

应用工厂沿用现有显式注册表，幂等注册：

- `PersonalUsageHandler`
- `PublicUsageHandler`
- `PersonalReturnHandler`
- `PublicReturnHandler`

不增加自动发现、插件扫描或额外抽象。

### 2.3 权限种子

新增：

| 权限 | 默认角色 |
| --- | --- |
| `asset:usage:manage` | `SUPER_ADMIN`、`ASSET_ADMIN` |
| `asset:return:self` | `SUPER_ADMIN`、`ASSET_ADMIN`、`USER` |

这样资产管理员负责领用与验收，所有内置角色仍可归还自己持有的资产。权限名称分别为“管理资产领用退库”和“归还本人资产”，模块统一为 `asset`。

### 2.4 迁移拆分

使用 `005_asset_usage_return.py`，不再使用原计划的 `005_parallel_operation_features.py`。原因是调拨和维修尚未实现；把未完成模块绑定到同一已合入迁移会迫使后续修改历史迁移。未来功能各自使用新的顺序迁移。

迁移创建：

- `asset_usage_requests`
- `asset_return_requests`
- `asset_return_items`

列、JSON 快照、外键、唯一索引和普通索引与 SQLAlchemy 模型保持一致。降级先按依赖逆序删除表，再移除本迁移的角色权限关联和权限，不改动 001–004 的数据与结构。

## 3. 验证策略

先写集成失败测试，再实现注册和迁移。完成后执行：

1. SQLite 从空库升级到 head、降级到 004、再次升级；
2. Ruff、format、mypy、conventions guard 和全量 pytest；
3. 实际 Flask 启动与 HTTP smoke，确认正式路由可达、生产配置不暴露 mock 路由；
4. 使用现有外部 MySQL 配置时，优先在独立临时 schema 验证 upgrade/downgrade，不触碰现有业务 schema；若账号无建库权限，明确记录阻塞；
5. 独立审查线程从六个维度只读验证，主线程按清单修复并由同一线程复验。
