# 资产台账三页面并行开发设计

## 1. 目标与范围

本轮在现有资产系统主题、AppShell 和首页基础上，完成资产台账域的三个核心页面：

- 资产列表；
- 资产详情；
- 资产新增与编辑。

三个页面并行开发，但必须先冻结共享资产契约，并严格限制共享文件的修改者。业务流程页面、真实文件上传、跨页批量编辑和后端实现不在本轮范围内。

## 2. 路由与导航

本轮增加以下受保护路由：

```text
/assets                     资产列表
/assets/new                 新增资产
/assets/:assetId            资产详情
/assets/:assetId/edit       编辑资产
```

`/assets/new` 必须在 `/:assetId` 之前注册，避免把 `new` 解析为资产 ID。资产台账导航项从禁用状态改为可用。其它尚未实现的模块继续保持禁用状态。

## 3. 并行开发边界

### 3.1 主任务独占文件

主任务负责创建并冻结共享层，三个页面任务不得修改这些文件：

```text
src/features/assets/types.ts
src/features/assets/assetModel.ts
src/features/assets/assetModel.test.ts
src/features/assets/assetData.ts
src/api/assets.ts
src/router/index.tsx
src/config/navigation.ts
src/i18n/zhCN.ts
```

主任务还负责最终集成、冲突处理、全量验证和浏览器 QA。

### 3.2 列表页面任务

仅修改：

```text
src/features/assets/list/**
src/pages/Assets.tsx
```

### 3.3 详情页面任务

仅修改：

```text
src/features/assets/detail/**
src/pages/AssetDetail.tsx
```

### 3.4 新增/编辑页面任务

仅修改：

```text
src/features/assets/form/**
src/pages/AssetForm.tsx
```

三个页面任务不得新增全局依赖，不得修改主题、AppShell、导航、路由、通用 HTTP 客户端或其它页面。

## 4. 共享资产契约

### 4.1 资产核心字段

共享类型至少覆盖：

- `id`；
- `asset_code`；
- `asset_name`；
- `category_name`；
- `status`；
- `model`；
- `serial_number`；
- `receipt_number`；
- `user_name`；
- `department_name`；
- `location_name`；
- `manager_name`；
- `company_name`；
- `supplier_name`；
- `source_name`；
- `unit_name`；
- `purchase_date`；
- `purchase_amount`；
- `zero_amount_reason`；
- `information_complete`；
- `remark`；
- `created_at`；
- `updated_at`。

字段名保持后端 Schema 的 snake_case，不在前端静默转换。

### 4.2 状态

第一版展示状态：

```text
IDLE          闲置
IN_USE        在用
REPAIRING     维修中
SCRAPPED      已报废
```

状态标签的文案、颜色和排序通过共享模型集中定义，页面不得各自维护一套映射。

### 4.3 数据访问

`src/api/assets.ts` 是未来真实 API 的唯一入口。页面不直接访问 `@/api/http`，而是调用资产 API 函数。

后端接口尚未稳定时，使用 `assetData.ts` 中集中、带类型的演示数据。API 层暴露 Promise 形式的数据函数，使页面从第一天起通过 React Query 管理加载、错误、缓存和重新获取。接入真实接口时，只替换 API 函数内部实现。

建议接口：

```ts
listAssets(query): Promise<PageResult<AssetSummary>>
getAsset(assetId): Promise<AssetDetail>
createAsset(payload): Promise<AssetDetail>
updateAsset(assetId, payload): Promise<AssetDetail>
```

## 5. 资产列表设计

### 5.1 搜索与筛选

页面顶部包含：

- 快速搜索：资产编码、名称、序列号、使用人和收货单号的包含匹配；
- 多编码精确查询：支持换行、逗号和空格分隔，自动去重；
- 常用筛选：公司、分类、状态、部门、地点和信息完整状态；
- 更多筛选抽屉：使用人、责任管理员、供应商、来源和购入日期；
- 重置和查询操作。

筛选值属于页面 UI 状态，查询结果属于 React Query 远端状态。只有点击查询或分页变化时更新查询键，避免输入每个字符都发请求。

### 5.2 桌面端

使用 AntD Table，默认列严格按照需求文档：

- 资产编码；
- 名称；
- 分类；
- 状态；
- 使用人；
- 使用部门；
- 地点；
- 责任管理员；
- 所属公司；
- 购入日期。

金额默认不显示。没有 `asset:amount:view` 权限时，金额列不进入列配置选项。

### 5.3 移动端

移动端不横向压缩桌面表格，改为资产卡片列表。每张卡片显示编码、名称、状态、分类、使用人或地点，并提供进入详情的操作。

### 5.4 分页与选择

- 默认每页 50 条；
- 可选 20、50、100 条；
- 当前页选择使用 AntD 行选择；
- 本轮只实现当前页选择状态和“选择全部筛选结果”的二次确认界面，不执行真实批量业务。

## 6. 资产详情设计

详情页顶部显示资产编码、名称、状态、分类、所属公司和主要操作。资产编码始终只读。

标签页固定为：

1. 基本信息；
2. 照片附件；
3. 主附资产；
4. 资产履历；
5. 维修记录；
6. 报废信息；
7. 盘点记录；
8. 相关审批。

本轮完整展示基本信息。其它标签页使用结构化空状态或演示记录，不实现上传、维修、报废、盘点和审批操作。

桌面端基本信息使用两到三列描述布局；移动端使用单列信息流。金额字段只在拥有 `asset:amount:view` 权限时渲染。

## 7. 新增与编辑设计

新增和编辑复用同一套表单字段与验证 Schema：

- React Hook Form 管理表单；
- Zod 定义校验；
- AntD 只负责布局和输入控件；
- 不重复编写 AntD `rules`。

表单按以下区块组织：

1. 基础信息；
2. 归属与位置；
3. 采购信息；
4. 管理信息；
5. 备注。

新增时资产编码由系统生成，页面显示生成规则提示但不允许手工输入。编辑时资产编码展示为只读字段。状态、使用人、部门和已有地点默认不进入普通编辑；本轮只展示只读业务状态，避免绕过后续业务流程。

页面新增必填字段包括资产名称、所属公司、资产分类、资产来源、计量单位、购入日期、存放地点和责任管理员；供应商可选。金额不能为负数；零金额必须填写原因。

提交成功后进入资产详情；提交失败保留用户输入并显示统一错误状态。取消操作返回上一页，有未保存修改时需要二次确认。

## 8. 加载、空状态和错误处理

- 三个页面均提供与最终布局相近的 Skeleton；
- 列表无结果使用统一空状态，并保留当前筛选条件；
- 详情不存在时显示“资产不存在或无权查看”，不泄露具体权限原因；
- 模块请求失败只影响当前页面，并提供重试；
- 表单提交错误通过 React Query mutation 状态展示；
- 鉴权失败继续由统一 HTTP 拦截器处理。

## 9. 兼容性与性能

- 不使用 CSS `gap`、`position: sticky`、毛玻璃、容器查询和复杂滤镜；
- 大列表只渲染当前分页数据；
- 筛选和列配置避免频繁深拷贝；
- 页面级组件继续懒加载；
- 新浏览器 API 必须特性检测并提供降级；
- 触摸目标不小于 44px；
- 复杂表格不直接缩小为手机布局。

## 10. 测试与验收

共享模型测试覆盖：

- 多编码解析、去重和空值处理；
- 状态映射；
- 筛选匹配；
- 分页边界；
- 金额字段权限；
- 新增/编辑 payload 归一化。

页面任务各自提供框架无关的纯逻辑测试。最终运行：

```bash
cd front
npm test
npm run type-check
npm run lint
npm run build
```

浏览器 QA 覆盖：

- 列表查询、筛选、分页和进入详情；
- 详情标签切换和编辑入口；
- 新增/编辑校验、取消确认和成功跳转；
- 桌面端、小屏笔记本和手机宽度；
- 控制台无相关 error/warning；
- 与既有浅色设计系统一致。

## 11. 集成顺序

1. 主任务提交共享资产契约与测试；
2. 三个页面任务并行开发，禁止修改共享文件；
3. 主任务逐一审查三个页面产出；
4. 主任务统一修改路由、导航和 i18n；
5. 运行全量检查并修复集成问题；
6. 完成浏览器视觉与交互 QA。

## 12. 明确不做

本轮不实现：

- 真实附件上传和删除；
- 资产批量编辑执行；
- 跨页批量业务执行；
- 领用、退库、转移、维修、报废、盘点和审批流程；
- 后端接口、数据库或迁移修改；
- 新增 UI 或图表依赖；
- 深色主题。
