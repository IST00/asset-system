# `doLogin` 类型速查

## 函数签名

```ts
doLogin(
  params?: WebLoginParam & AuroraLoginParam & NativeLoginParam & PopupLoginFormProps
): Promise<UserInfo>
```

---

## `WebLoginParam`

继承自 `LoginFormProps`，添加弹框展示相关字段。

```ts
type WebLoginParam = LoginFormProps & {
  visible?: boolean;
  zIndex?: number;
  showClose?: boolean;
  maskClose?: boolean;
  backgroundColor?: string;
  sensors?: any;
  onClose?: (userInfo?: UserInfo) => void;
};
```

### `LoginFormProps`（表单 UI 配置）

```ts
type LoginFormProps = {
  className?: string;
  style?: React.CSSProperties;
  title?: React.ReactNode | string | null | undefined;
  footer?: React.ReactNode | string | null | undefined;
  banner?: React.ReactNode | string | null | undefined;
  buttonText?: React.ReactNode | string | null | undefined;
  autoFocus?: boolean;
  disabled?: boolean;
  login?: boolean;
  agreement?: AgreementLinkList[];

  prefix?: string;
  postfix?: string;
  onBeforeSendSMS?: (info: Record<string, string>) => Promise<void>;
  onBeforeLogin?: (mobile?: string) => void;
  onLogin?: (userInfo: UserInfo) => void;
  onError?: (error: Error) => void;
  onBlur?: (type: string) => void;
};
```

---

## `AuroraLoginParam`

```ts
type AuroraLoginParam = {
  customUIWithConfig?: SetCustomUIWithConfigParams;
};
```

### `SetCustomUIWithConfigParams`（Aurora 一键登录界面定制）

```ts
type SetCustomUIWithConfigParams = {
  logo?: string;               // 品牌 logo URL
  appName?: string;            // 应用名称
  loginBtnColor?: string;      // 登录按钮背景色（hex）
  loginTextColor?: string;     // 登录按钮文字颜色（hex）
  customPolicyLinkColor?: string; // 协议链接颜色（hex）
  customPolicyLink1?: [string, string]; // [协议文案, 协议链接]
};
```

---

## `NativeLoginParam`

```ts
type NativeLoginParam = {
  allowEmptyToken?: boolean; // 允许空 token（游客态），默认 true
  init?: boolean;            // true → CoreNative.init，false → CoreNative.login
};
```

---

## `PopupLoginFormProps`（弹框扩展参数）

```ts
type PopupLoginFormProps = {
  logout?: boolean;            // 已登录时强制重新登录
  source?: string;
  activityType?: string;
  activityId?: number;
  encryptActivityId?: string;
  trackingSourceId?: number;
};
```

---

## `UserInfo`（返回值）

```ts
// 来源：src/app/user/types.ts
type UserInfo = {
  token?: string;
  userId?: string | number;
  nickname?: string;
  avatar?: string;
  isLoading?: boolean;
  newUser?: boolean;
  // ... 其余用户属性
};
```

---

## `LoginParams`（推广参数，通过 `updateLoginParams` 写入）

```ts
type LoginParams = {
  c?: string;              // 渠道码
  r?: string;              // 推广人加密 ID
  activityType?: string;
  activityId?: string;
  trackingSourceId?: number;
  source?: string;
  secondSource?: string;
  sourceId?: string;
  channel?: string;
  authType?: number;       // 登录认证方式枚举（见下方）
  childId?: string;        // 海报 ID
  copyId?: string;         // 文案 ID
};
```

---

## `authType` 枚举

| 值 | 说明 |
|----|------|
| 2  | 微信授权登录（App 与 Web） |
| 4  | 手机号验证码登录（默认 H5） |
| 9  | 微信小程序 |
| 14 | 极光一键登录（Aurora） |

---

## `AgreementLinkList`

```ts
type AgreementLinkList = {
  title: string; // 协议标题（展示用）
  label: string; // 协议标签（短名称）
  link: string;  // 协议链接 URL
};
```
