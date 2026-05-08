# Login 示例（`app.login`）

假定已注入 `window.SoybeanCommonMain.alias`。

## 基础登录流程

### 1. 自动选择最优登录方式

```tsx
const {app} = window.SoybeanCommonMain.alias;

async function handleLogin() {
  try {
    const userInfo = await app.login.action.doLogin({
      // 可选：传递登录参数
      sensors: {
        source: 'home_page',
        title: '首页',
      },
      onBeforeLogin: async () => {
        console.log('登录前回调');
      },
    });

    console.log('登录成功', userInfo);
  } catch (error) {
    console.error('登录失败', error);
  }
}
```

### 2. 强制使用 Web 表单登录

```tsx
const {app} = window.SoybeanCommonMain.alias;

async function handleWebLogin() {
  try {
    const userInfo = await app.login.action.doLogin({
      visible: true,           // 显示弹窗
      showClose: true,         // 显示关闭按钮
      maskClose: false,        // 禁止点击蒙层关闭
      title: '欢迎登录',       // 自定义标题
      buttonText: '立即登录',  // 自定义按钮文字
      onClose: (userInfo) => {
        if (userInfo) {
          console.log('登录成功并关闭', userInfo);
        } else {
          console.log('用户取消登录');
        }
      },
    });
  } catch (error) {
    console.error('登录失败', error);
  }
}
```

## 获取手机号但不登录

### 使用 doPopupLoginForm（仅获取验证码）

```tsx
const {app} = window.SoybeanCommonMain.alias;

async function handleGetMobile() {
  try {
    // 弹窗表单但不执行登录
    const result = await app.login.action.doPopupLoginForm({
      title: '请输入手机号',
      buttonText: '下一步',
      login: false, // 关键：不执行登录
      onBeforeSendSMS: async (info) => {
        console.log('发送验证码前', info);
      },
    });

    // 手动读取表单数据
    const mobile = app.login.store.$mobile.get();
    const verificationCode = app.login.store.$verificationCode.get();
    const areaCode = app.login.store.$areaCode.get();

    console.log('手机号', mobile.value);
    console.log('验证码', verificationCode.value);
    console.log('区号', areaCode.value);

    // 后续业务逻辑...
  } catch (error) {
    console.error('取消输入', error);
  }
}
```

## 更新登录参数

### 设置渠道、活动、来源

```tsx
const {app} = window.SoybeanCommonMain.alias;

// 在登录前更新参数
app.login.action.updateLoginParams({
  c: 'app_share',           // 渠道
  r: 'user_123',            // 推广人 ID
  activityId: 'activity_1', // 活动 ID
  trackingSourceId: 1001,   // 注册来源 ID
  source: 'promotion',      // 短信来源
  sourceId: 'book_456',     // 书籍 ID
});

// 然后调用登录
await app.login.action.doLogin();
```

### 动态获取注册来源 ID

```tsx
const {app} = window.SoybeanCommonMain.alias;

// 获取注册来源 ID（按优先级自动选择）
const trackingSourceId = await app.login.action.getTrackingSourceId();
console.log('注册来源 ID', trackingSourceId);

// 或手动更新
app.login.action.updateTrackingSourceId(2001);
```

## 手动校验与表单操作

### 校验手机号和协议

```tsx
const {app} = window.SoybeanCommonMain.alias;

function validateForm() {
  try {
    // 校验手机号
    app.login.action.validateMobile();

    // 校验协议
    app.login.action.validateAgreement();

    // 或一次性校验全部
    app.login.action.validate();

    console.log('校验通过');
  } catch (error) {
    console.error('校验失败', error.message);
  }
}
```

### 手动更新字段

```tsx
const {app} = window.SoybeanCommonMain.alias;

// 更新手机号
app.login.action.updateField('$mobile', '13800138000');

// 更新验证码
app.login.action.updateField('$verificationCode', '123456');

// 更新协议勾选状态
app.login.action.updateField('$agreement', true);

// 更新区号
app.login.action.updateField('$areaCode', '86');
```

### 清除错误状态

```tsx
const {app} = window.SoybeanCommonMain.alias;

// 清除手机号错误
app.login.action.clearError(app.login.store.$mobile);

// 清除验证码错误
app.login.action.clearError(app.login.store.$verificationCode);
```

## 发送验证码

```tsx
const {app} = window.SoybeanCommonMain.alias;

async function handleSendSMS() {
  try {
    // 首次发送
    await app.login.action.sendSMS({isFirstTime: true});

    // 或重新发送
    await app.login.action.sendSMS({isFirstTime: false});

    console.log('验证码已发送');
  } catch (error) {
    console.error('发送失败', error.message);
  }
}
```

## React Hooks 订阅状态

### 监听表单字段变化

```tsx
import {useEffect} from 'react';

const {app} = window.SoybeanCommonMain.alias;

function LoginObserver() {
  const mobile = app.login.context.useMobile();
  const verificationCode = app.login.context.useVerificationCode();
  const agreement = app.login.context.useAgreement();
  const areaCode = app.login.context.useAreaCode();

  useEffect(() => {
    console.log('手机号变化', mobile);
  }, [mobile]);

  useEffect(() => {
    console.log('验证码变化', verificationCode);
  }, [verificationCode]);

  return (
    <div>
      <p>手机号: {mobile.value}</p>
      <p>验证码: {verificationCode.value}</p>
      <p>协议已勾选: {agreement.value ? '是' : '否'}</p>
      {mobile.error && <p style={{color: 'red'}}>{mobile.message}</p>}
    </div>
  );
}
```

### 使用 nanostores 订阅

```tsx
const {app} = window.SoybeanCommonMain.alias;

// 订阅手机号变化
const unsubscribe = app.login.action.subscribe('$mobile', () => {
  const mobile = app.login.store.$mobile.get();
  console.log('手机号更新', mobile.value);
});

// 取消订阅
unsubscribe();
```

## 弹窗用户协议

```tsx
const {app} = window.SoybeanCommonMain.alias;

async function showAgreement() {
  const isAgree = await app.login.action.doPopupAgreement({
    title: '用户协议与隐私政策',
    content: '请仔细阅读并同意以下协议',
    comfirmText: '同意',
    cancelText: '取消',
    linkList: [
      {
        title: '《用户协议》',
        label: '用户协议',
        link: 'https://example.com/user-agreement',
      },
      {
        title: '《隐私政策》',
        label: '隐私政策',
        link: 'https://example.com/privacy-policy',
      },
    ],
  });

  if (isAgree) {
    console.log('用户同意协议');
    app.login.action.updateField('$agreement', true);
  } else {
    console.log('用户拒绝协议');
  }
}
```

## 使用登录组件

### BasicLoginForm（基础表单）

```tsx
const {app} = window.SoybeanCommonMain.alias;
const {BasicLoginForm} = app.login.components;

function LoginPage() {
  return (
    <BasicLoginForm
      title="欢迎登录"
      buttonText="登录"
      autoFocus={true}
      onLogin={(userInfo) => {
        console.log('登录成功', userInfo);
      }}
      onError={(error) => {
        console.error('登录失败', error);
      }}
      onBeforeSendSMS={async (info) => {
        console.log('发送验证码前', info);
      }}
    />
  );
}
```

### PopupLoginForm（弹窗表单）

```tsx
const {app} = window.SoybeanCommonMain.alias;

// 通过 action 调用（推荐）
await app.login.action.doLogin({
  visible: true,
  showClose: true,
  title: '登录',
  onClose: (userInfo) => {
    console.log('关闭弹窗', userInfo);
  },
});
```

## 完整登录流程示例

```tsx
const {app} = window.SoybeanCommonMain.alias;

async function completeLoginFlow() {
  try {
    // 1. 设置登录参数
    app.login.action.updateLoginParams({
      c: 'homepage',
      activityId: 'spring_festival',
      trackingSourceId: 1001,
    });

    // 2. 唤起登录
    const userInfo = await app.login.action.doLogin({
      title: '欢迎来到帆书',
      buttonText: '登录/注册',
      sensors: {
        source: 'homepage',
        title: '首页登录',
      },
      onBeforeLogin: async (mobile) => {
        console.log('即将登录', mobile);
        // 可在此执行埋点等操作
      },
      onLogin: (userInfo) => {
        console.log('登录成功回调', userInfo);
      },
      onError: (error) => {
        console.error('登录失败回调', error);
      },
    });

    // 3. 登录成功后处理
    console.log('用户信息', userInfo);
    console.log('Token', userInfo.token);
    console.log('是否新用户', userInfo.newUser);

    // 4. 跳转到目标页面
    window.location.href = '/dashboard';
  } catch (error) {
    console.error('登录流程异常', error);
  }
}
```

## 重置表单

```tsx
const {app} = window.SoybeanCommonMain.alias;

// 重置所有表单字段到默认值
app.login.action.reset();
```

## 检查字段错误

```tsx
const {app} = window.SoybeanCommonMain.alias;

const hasError = app.login.action.isFieldError();
if (hasError) {
  console.log('表单存在错误');
}
```

## 获取拼装后的手机号

```tsx
const {app} = window.SoybeanCommonMain.alias;

const mobile = app.login.store.$mobile.get();
const areaCode = app.login.store.$areaCode.get();

const fullMobile = app.login.action.getComputedMobile(areaCode.value, mobile.value);
console.log('完整手机号', fullMobile); // 如 +8613800138000 或 13800138000
```
