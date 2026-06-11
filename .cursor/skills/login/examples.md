# `doLogin` 使用示例

## 1. 基础调用（最常见）

```ts
const {app} = window.SoybeanCommonMain.alias;

// 直接调用即可：已登录 → 直接返回 userInfo；未登录 → 自动弹框
// 业务方无需自行判断登录状态
const userInfo = await app.login.action.doLogin();
console.log(userInfo.token, userInfo.userId);
```

---

## 2. 带埋点来源

```ts
const userInfo = await app.login.action.doLogin({
  sensors: {
    source: 'home_banner',
    title: '首页 Banner 登录入口',
  },
});
```

---

## 3. 强制重新登录（已登录也弹框）

```ts
const userInfo = await app.login.action.doLogin({logout: true});
```

---

## 4. 处理用户取消

```ts
try {
  const userInfo = await app.login.action.doLogin({
    cancelText: '您取消了登录',
  });
  // 登录成功
  handleLoginSuccess(userInfo);
} catch (err) {
  if (err.message === '您取消了登录') {
    // 用户主动关闭弹框
  } else if (err.message === '用户取消授权') {
    // Aurora 一键登录：用户拒绝授权
  }
}
```

---

## 5. 预置推广参数后登录

```ts
// 在调用 doLogin 前写入推广信息
app.login.action.updateLoginParams({
  r: encryptedUserId,   // 推广人 ID
  c: channelCode,       // 渠道码
  activityId: 'act_001',
  trackingSourceId: 1001,
});

const userInfo = await app.login.action.doLogin();
```

---

## 6. Aurora 一键登录 — 自定义界面

```ts
const userInfo = await app.login.action.doLogin({
  customUIWithConfig: {
    logo: 'https://cdn.example.com/logo.png',
    appName: '我的 App',
    loginBtnColor: '#FF5500',
    loginTextColor: '#FFFFFF',
  },
  onBeforeLogin: async () => {
    // 登录接口调用前执行，例如上报埋点
    await trackEvent('aurora_login_confirm');
  },
});
```

---

## 7. Native App 初始化登录

```ts
// init 模式：App 冷启动时调用 CoreNative.init
const userInfo = await app.login.action.doLogin({
  init: true,
  allowEmptyToken: true, // 允许空 token（游客态）
});
```

---

## 8. 指定弹框挂载容器

```ts
// 挂载到指定 DOM 元素（适用于局部弹框场景）
const userInfo = await app.login.action.doLogin({
  el: document.getElementById('login-root'),
});
```

---

## 9. 在 React 组件中使用

```tsx
function LoginButton() {
  const {app} = window.SoybeanCommonMain.alias;

  const handleClick = async () => {
    try {
      const userInfo = await app.login.action.doLogin({
        sensors: {source: 'profile_page'},
      });
      // 更新组件状态
      setUserInfo(userInfo);
    } catch {
      // 用户取消，忽略
    }
  };

  return <button onClick={handleClick}>立即登录</button>;
}
```
