---
name: sensors
description: >-
  Documents Soybean common main `app.sensors` on `window.SoybeanCommonMain.alias`:
  `track`, `registerPage`, `registerQuery`, `registerUser`, and login binding to
  `window.sensors`. Use when adding analytics, page context, or debugging sensors.
---

# Sensors（`window.SoybeanCommonMain.alias.app.sensors`）

> **⚠️ 仅限 Web H5 页面使用**
> 本 Skill 依赖 `window.SoybeanCommonMain`，只能在 Web H5 页面环境（`front/` 目录下的页面）中使用，不适用于后端或其他非 H5 场景。

已接入 common main 时：**埋点入口**优先 `app.sensors`，底层仍委托 `window.sensors`，字段拼装与注册集中管理。

## 快速开始

1. 业务侧默认 **`track`** / **`registerPage`**；`login` / `registerQuery` / `registerUser` 已经由内置流程在页面初始化时、登录完成后执行了，**勿重复调用**以免覆盖上下文。
2. `track(key, params)`：`key` 由业务侧自定义。
3. **`track` 示例**见 [examples.md](examples.md)。

## 何时使用

- 上报点击/曝光/浏览；注册预置属性。

## 能力速查

| API | 用途 |
| --- | --- |
| `track(key, params)` | 单条行为事件 |
| `registerPage(query)` | 注册预置属性 |
| `registerQuery()` | 注册固定的预置属性函数（内置已调） |
| `login(userId)` | 绑定用户 ID（内置已调） |
| `registerUser(userInfo)` | 注册固定的预置属性函数以及绑定用户 ID（内置已调） |

## 内置字段（了解即可）

- **`registerQuery`**：`platform_type`、`refer_page` / `refer_id` / `refer_name`、`source_r`（缺省为空串）。
- **`registerUser`**：按 `userRoleCode` 等映射 `status`、`ff_status`、`lilei_status`、`belong` 等后 `login`。

## 常见问题

| 现象 | 方向 |
| --- | --- |
| 无上报 | `key`、是否触发、`window.sensors` 是否存在 |
| 来源字段缺 | 内置初始化是否执行；链接是否带 `refer_*` / `r` |

## 实践建议

**应做**：事件命名稳定；默认只 `track`。

**避免**：无评审理由重复 `login` / `registerPage` / `registerQuery` / `registerUser`。

## 延伸阅读

- [examples.md](examples.md) — `track`、`registerPage` 示例
