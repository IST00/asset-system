# Skills 索引

本目录包含 Soybean Common Main React 公共库的 AI Agent Skills，用于指导 AI 工具正确集成和使用公共模块。

## 📋 Skills 列表

### 🔐 [login](./login/SKILL.md)

登录与认证模块，封装完整的用户登录流程。

**核心功能**：
- 登录表单弹窗（`doPopupLoginForm`）
- 用户协议弹窗（`doPopupAgreement`）
- 登录执行（`doLogin`）
- 登录态管理与同步

**适用场景**：
- 实现登录/注册功能
- 处理用户认证流程
- 调试登录 UX 问题
- 集成用户协议确认

**别名路径**：`window.SoybeanCommonMain.alias.app.login`

[查看详细文档](./login/SKILL.md) | [查看示例代码](./login/examples.md)

---

### 📊 [sensors](./sensors/SKILL.md)

神策（Sensors Data）埋点模块，提供统一的数据追踪接口。

**核心功能**：
- 事件追踪（`track`）
- 页面上下文注册（`registerPage`）
- URL 参数注册（`registerQuery`）
- 用户信息绑定（`registerUser`）
- 登录关联埋点

**适用场景**：
- 添加业务埋点
- 管理页面分析上下文
- 调试埋点问题
- 追踪用户行为

**别名路径**：`window.SoybeanCommonMain.alias.app.sensors`

[查看详细文档](./sensors/SKILL.md) | [查看示例代码](./sensors/examples.md)

---

## 🎯 如何使用

### 1. AI Agent 自动识别

当你在对话中提到相关功能时，AI 会自动加载对应的 skill：

- 提到 "登录"、"认证"、"用户注册" → 自动加载 `login` skill
- 提到 "埋点"、"神策"、"数据追踪" → 自动加载 `sensors` skill

### 2. 手动引用 Skill

在对话中直接 @ 引用：

```
@.cursor/skills/login/SKILL.md 如何实现微信登录？
@.cursor/skills/sensors/SKILL.md 如何添加按钮点击埋点？
```

### 3. 查看示例代码

每个 skill 都包含 `examples.md`，提供完整的使用示例：

- [登录模块示例](./login/examples.md)
- [埋点模块示例](./sensors/examples.md)

---

## 📦 依赖关系

```
@soybean/common.main.react
  └── window.SoybeanCommonMain.alias
        ├── app.login          (login skill)
        └── app.sensors        (sensors skill)
```

---

## 🔗 相关文档

- **项目根文档**：[`../../CLAUDE.md`](../../CLAUDE.md)
- **约定规范**：[`../../docs/conventions/`](../../docs/conventions/)
- **Soybean 公共库**：`@soybean/common.main.react`

---

## 🤝 贡献指南

新增 skill 时，请遵循以下结构：

```
.cursor/skills/<模块名>/
  ├── SKILL.md        # skill 主文档（必需）
  ├── examples.md     # 使用示例（推荐）
  └── reference.md    # API 参考（可选）
```

**SKILL.md 必需包含**：
- YAML front matter（name + description）
- 功能概述
- 核心 API 说明
- 使用场景
- 触发关键词

---

*最后更新：2026-05-08*
