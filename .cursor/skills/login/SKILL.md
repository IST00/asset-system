---
name: login-do-login
description: >-
  Documents Soybean common main `app.login` on `window.SoybeanCommonMain.alias`:
  `doLogin`（统一登录入口，自动路由 Native / Aurora 一键登录 / H5 弹框）。
  Use when implementing login flows, triggering the login popup, or debugging
  `doLogin` / `doNativeLogin` / `doAuroraLogin` / `doWebLogin` behavior.
---

# Login · `doLogin`（`window.SoybeanCommonMain.alias.app.login`）

> **⚠️ 仅限 Web H5 页面使用**
> 本 Skill 依赖 `window.SoybeanCommonMain`，只能在 Web H5 页面环境（`front/` 目录下的页面）中使用，不适用于后端或其他非 H5 场景。

## 快速开始

```ts
const {app} = window.SoybeanCommonMain.alias;

// 直接调用即可，无需提前判断登录状态
const userInfo = await app.login.action.doLogin(params?);
```

`doLogin` 是统一入口，有两点**不需要业务方自行判断**：

1. **登录状态**：已登录则直接返回 `userInfo`，未登录才弹框——业务方无需 `if (token)` 守卫。
2. **运行环境**：内部自动路由登录方式，无需区分 Native / H5。

| 运行环境 | 实际走的登录方式 |
|----------|----------------|
| Native App | `doNativeLogin` → JSBridge |
| H5 + Aurora SDK 可用 | `doAuroraLogin` → 极光一键登录，失败降级 `doWebLogin` |
| H5 + Aurora 不可用 | `doWebLogin` → 手机号验证码弹框 |

---

## 参数说明

```ts
doLogin(params?: WebLoginParam & AuroraLoginParam & NativeLoginParam & PopupLoginFormProps): Promise<UserInfo>
```

所有参数均为**可选**。常用字段：

| 参数 | 类型 | 说明 |
|------|------|------|
| `logout` | `boolean` | 已登录时强制重新弹登录框（默认跳过） |
| `sensors` | `{source?: string; title?: string; ...}` | 埋点来源信息 |
| `onBeforeLogin` | `() => Promise<void>` | 登录接口调用前的钩子（Aurora 流程） |
| `customUIWithConfig` | `SetCustomUIWithConfigParams` | Aurora 一键登录界面自定义（logo / 颜色等） |
| `el` | `string \| Element` | 挂载 H5 弹框的容器（不传则自动创建） |
| `cancelText` | `string` | 用户关闭弹框时 reject 的错误消息文本 |
| `allowEmptyToken` | `boolean` | Native：允许空 token（默认 `true`） |
| `init` | `boolean` | Native：使用 `CoreNative.init` 而非 `CoreNative.login` |

> 完整类型定义见 [reference.md](reference.md)。

---

## 返回值与错误处理

- **成功**：resolve `UserInfo`（含 `token`、`userId` 等用户信息）。
- **用户主动关闭弹框**：reject，message 为 `cancelText`（默认 `undefined`）。
- **Aurora 用户取消授权**：reject，message 为 `'用户取消授权'`。

```ts
try {
  const userInfo = await app.login.action.doLogin({
    sensors: {source: 'home_banner'},
  });
  console.log(userInfo.token);
} catch (err) {
  // 用户取消 / 关闭弹框
  console.warn(err.message);
}
```

---

## 已登录时的行为

```ts
// 已登录 → 直接返回缓存 userInfo，不弹框
const userInfo = await doLogin();

// 强制重新登录（已登录也弹框）
const userInfo = await doLogin({logout: true});

// 登录中（isLoading）→ 等待当前请求完成后返回
```

---

## 约束与依赖

- 依赖 `window.SoybeanCoreMain`（`native` / `CoreNative`）与 `window.SoybeanCommonMain`。
- Aurora 一键登录需 Aurora SDK 在宿主页面初始化（`aurora.enableUse()` 返回 `true`）。
- `doNativeLogin` 要求 App 端支持 `CoreNative.login` / `CoreNative.init`。
- `loginParams`（推广信息：`r` / `c` / `activityId` 等）通过 `app.login.action.updateLoginParams` 预先写入，`doLogin` 内部自动读取。

---

## 常见问题

| 现象 | 排查方向 |
|------|----------|
| 已登录但仍弹框 | 检查 `userInfo.token` 是否有值；或传了 `logout: true` |
| Aurora 每次都降级 H5 | `aurora.enableUse()` 返回 `false`，确认 Aurora SDK 已初始化 |
| Native 登录 token 为空 | `allowEmptyToken: false` 时会 reject，检查 App 侧授权 |
| 弹框挂载位置不对 | 传入 `el` 指定容器，否则自动 `appendChild` 到 `document.body` |
| 推广参数丢失 | 在 `doLogin` 之前调用 `updateLoginParams({r, c, ...})` |

## 延伸阅读

- [examples.md](examples.md) — 基础调用、强制登录、Aurora 自定义 UI 示例
- [reference.md](reference.md) — `WebLoginParam` / `NativeLoginParam` / `UserInfo` 类型速查
