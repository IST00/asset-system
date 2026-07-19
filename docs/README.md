# 项目文档索引

## 产品需求

- [`product/资产系统建设方案.md`](./product/资产系统建设方案.md)：资产系统完整建设方案和需求确认记录。
- [`product/README.md`](./product/README.md)：需求解释顺序、当前技术实现差异和 AI 使用规则。

## 工程约定

- [`conventions/backend.md`](./conventions/backend.md)：Flask 后端分层、API 和数据访问约定。
- [`conventions/frontend.md`](./conventions/frontend.md)：React 前端工程约定。
- [`conventions/middleware.md`](./conventions/middleware.md)：数据库、健康检查和可观测性约定。
- [`conventions/workflow.md`](./conventions/workflow.md)：分支、提交、CI 和脚手架变更流程。

## 设计与实施计划

- [`superpowers/plans/`](./superpowers/plans/)：已经确认的分阶段实施计划。

开发新功能前先读产品建设方案中的对应业务规则，再读相关工程约定；不得用建设方案中已经被当前仓库替换的技术选型覆盖现有项目结构。
