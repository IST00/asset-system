# Sensors 示例（`app.sensors`）

假定已注入 `window.SoybeanCommonMain.alias`。内置 `login` / `registerQuery` / `registerUser` 勿重复调用，内置 `registerPage`，无扩展字段勿重复调用，见 [SKILL.md](SKILL.md)。

## track

### 点击事件埋点

```tsx
const {app} = window.SoybeanCommonMain.alias;

function Page() {
  return (
    <button
      onClick={() =>
        app.sensors.track('web_example_click', {
          page_type: 'example_page',
          click_type: 'main_cta',
        })
      }
    >
      点击
    </button>
  );
}
```

### 页面加载事件埋点

```tsx
import {useEffect} from 'React'

const {app} = window.SoybeanCommonMain.alias;

function Page() {
  useEffect(() => {
    app.sensors.track('web_example_load', {
      page_type: 'example_page',
    })
  }, [])

  return <div></div>
}
```

## registerPage（按需，需保证在行为埋点之前执行）

```tsx
const {app} = window.SoybeanCommonMain.alias;

app.sensors.registerPage({
  page_name: 'example',
  // 其它页面级公共字段
});
```
