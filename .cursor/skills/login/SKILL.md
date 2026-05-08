---
name: login
description: >-
  Documents Soybean common main `app.login` on `window.SoybeanCommonMain.alias`:
  `doLogin`, `doPopupLoginForm`, `doPopupAgreement`, form fields, context hooks,
  store management, and login components. Use when implementing login flows,
  authentication, user registration, or debugging login UX.
---

# Login（`window.SoybeanCommonMain.alias.app.login`）

已接入 common main 时：**登录入口**统一 `app.login`，支持 Web 表单登录、极光一键登录、Native 原生登录三种方式，自动判断环境与能力。

## 快速开始

1. 业务侧默认调用 **`action.doLogin()`** 唤起登录流程，框架自动选择最优方式（极光/表单）。
2. 需要弹窗获取手机号但不立即登录时，使用 **`action.doPopupLoginForm()`**。
3. **登录流程示例**见 [examples.md](examples.md)。

## 何时使用

- 用户登录/注册；获取手机号与验证码；弹窗用户协议；登录状态校验；排查登录失败、验证码未发送、协议未勾选等问题。

## 能力速查

### action（核心方法）

| API | 用途 |
| --- | --- |
| `doLogin(params?)` | 唤起登录流程（自动选择极光/表单/Native） |
| `doPopupLoginForm(params)` | 弹窗登录表单（仅获取手机号验证码，不执行登录） |
| `doPopupAgreement(params)` | 弹窗用户协议 |
| `submitLoginForm(login)` | 提交登录表单（手动调用） |
| `sendSMS({isFirstTime})` | 发送验证码短信 |
| `validate()` | 校验表单完整性（手机号、验证码、协议） |
| `validateMobile()` | 仅校验手机号 |
| `validateAgreement()` | 仅校验协议勾选 |
| `reset()` | 重置表单字段 |
| `updateLoginParams(params)` | 更新登录参数（渠道、活动等） |
| `updateField(key, value, subKey?)` | 更新单个表单字段 |
| `clearError($store)` | 清除字段错误状态 |
| `throwError($store, message)` | 设置字段错误并抛异常 |
| `subscribe(key, callback)` | 订阅字段变化 |
| `getTrackingSourceId()` | 获取注册来源 ID（4 种来源优先级） |
| `updateTrackingSourceId(id)` | 更新注册来源 ID |
| `getActivityId()` | 获取活动 ID |
| `getComputedMobile(areaCode, mobile)` | 拼装国际号码格式 |
| `getAgreement()` | 获取协议勾选状态 |
| `isFieldError()` | 是否有字段错误 |

### store（状态管理）

| Store | 用途 |
| --- | --- |
| `$areaCode` | 区号字段（默认 +86） |
| `$mobile` | 手机号字段 |
| `$verificationCode` | 验证码字段 |
| `$agreement` | 协议勾选字段 |
| `$loginParams` | 登录参数（渠道、活动、来源等） |
| `$focusInput` | 输入框聚焦状态 |
| `$loginPosition` | 登录弹窗位置 |
| `defaults` | 字段默认值 |

### context（React Hooks）

| Hook | 用途 |
| --- | --- |
| `useAreaCode()` | 订阅区号状态 |
| `useMobile()` | 订阅手机号状态 |
| `useVerificationCode()` | 订阅验证码状态 |
| `useAgreement()` | 订阅协议勾选状态 |
| `useLoginParams()` | 订阅登录参数 |

### fields（表单组件）

| Component | 用途 |
| --- | --- |
| `AreaCodeSelect` | 区号选择器 |
| `MobileInput` | 手机号输入框 |
| `VerificationCodeInput` | 验证码输入框 |
| `CountDownButton` | 倒计时发送按钮 |
| `UserAgreement` | 用户协议勾选 |
| `LoginButton` | 登录按钮 |
| `FormTitle` | 表单标题 |
| `FormFooter` | 表单底部 |
| `ErrorMessage` | 错误提示 |

### components（整体组件）

| Component | 用途 |
| --- | --- |
| `BasicLoginForm` | 基础登录表单 |
| `PopupLoginForm` | 弹窗登录表单 |
| `AutoLoginForm` | 自动登录表单 |
| `CardLoginForm` | 卡片登录表单 |
| `PopupAgreement` | 协议弹窗 |

## 登录流程

### 1. 自动判断环境

```typescript
doLogin() → 
  Native 环境 → doNativeLogin()
  极光可用 → doAuroraLogin()
  其他 → doWebLogin()
```

### 2. 参数传递

```typescript
LoginParams {
  c?: string;              // 渠道
  r?: string;              // 推广人 ID
  activityId?: string;     // 活动 ID
  trackingSourceId?: number; // 注册来源 ID
  source?: string;         // 短信来源
  sourceId?: string;       // 书籍 ID
  childId?: string;        // 海报 ID
  copyId?: string;         // 文案 ID
}
```

### 3. 注册来源 ID 优先级

1. 通过 `updateLoginParams({ trackingSourceId })` 设置
2. 通过 URL 参数 `?trackingSourceId=xxx` 传递
3. 通过页面配置 `pageConfig.trackingSourceId` 获取
4. 通过活动容器配置获取

## 字段状态结构

```typescript
FieldAtom<T> {
  value: T;                 // 字段值
  error: boolean;           // 是否有错误
  message?: string;         // 错误信息
  name?: string;            // 国家名称（区号专用）
  abbr?: string;            // 国家缩写（区号专用）
}
```

## 常见问题

| 现象 | 方向 |
| --- | --- |
| 登录无反应 | 检查 `doLogin` 是否执行、环境判断是否正确 |
| 验证码未发送 | 手机号格式、`sendSMS` 是否调用、设备 ID 是否获取 |
| 协议未勾选报错 | `validateAgreement()` 校验、`$agreement.value` 状态 |
| 极光失败降级 | 检查 `aurora.loginAuth()` 错误、是否正确降级到 Web |
| 注册来源 ID 错误 | 检查 4 种来源优先级、`getTrackingSourceId()` 返回值 |
| 登录后未刷新用户信息 | 检查 `user.action.updateToken()` 调用 |

## 实践建议

**应做**：
- 默认使用 `doLogin()` 自动选择最优方式
- 手动调用 `updateLoginParams` 传递活动/渠道参数
- 登录前调用 `validate()` 校验完整性

**避免**：
- 跳过 `validateAgreement()` 校验
- 手动拼装 `LoginAPIParam`（使用 `submitLoginForm`）
- 重复调用 `reset()` 导致状态丢失

## 内置字段（了解即可）

- **区号默认值**：`+86` (中国)
- **验证码长度**：6 位
- **authType 枚举**：4=手机验证码，14=极光一键登录
- **短信 source 默认值**：`'login'`

## 延伸阅读

- [examples.md](examples.md) — `doLogin`、`doPopupLoginForm`、`doPopupAgreement` 示例
