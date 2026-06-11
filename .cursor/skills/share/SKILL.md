---
name: share
description: >-
  Documents Soybean common main `app.share` on `window.SoybeanCommonMain.alias`:
  `doSimpleShare`（基础分享面板）、`doMultiPosterShare`（多海报分享）、
  `useRegisterEffect`（微信 JSSDK 分享注册）。
  Use when implementing share flows, poster-based sharing, or WeChat share config.
---

# Share（`window.SoybeanCommonMain.alias.app.share`）

> **⚠️ 仅限 Web H5 页面使用**
> 本 Skill 依赖 `window.SoybeanCommonMain`，只能在 Web H5 页面环境（`front/` 目录下的页面）中使用，不适用于后端或其他非 H5 场景。

## 快速开始

```ts
const {app} = window.SoybeanCommonMain.alias;

// 基础分享面板
app.share.action.doSimpleShare(shareInfo, options?)

// 多海报分享（App 专属）
app.share.action.doMultiPosterShare(shareInfo, options?)

// 微信 H5 分享注册（在组件内调用）
app.share.context.useRegisterEffect(shareInfo)
```

## AI 实现分享时的默认行为

**默认使用 `doSimpleShare` 带单海报（`poster`）的分享方式。**

实现步骤：

1. **收集必填字段**：`title`、`desc`、`link`、`image`（分享卡片封面）。
2. **索取海报图片**：如果用户未提供海报图片，**必须先向用户提问**：
   > 请提供海报图片的可直接访问的 URL（支持 HTTPS 的 CDN 链接或 base64），用于生成分享海报。
3. **计算图片尺寸**：获得图片 URL 后，用 Shell 工具执行以下脚本获取真实宽高，然后：
   - 将 `poster.width` / `poster.height` 设为海报图片的原始宽高（画布尺寸由海报决定）。
   - 将 `poster.images[0]` 中的 `width` / `height` 同样设为该宽高，`x: 0, y: 0`（图片铺满画布）。

   ```bash
   bash .cursor/skills/share/get-image-size.sh "<IMAGE_URL>"
   ```

   脚本文件：[`get-image-size.sh`](get-image-size.sh)。
   输出 `{"width":750,"height":1334}` 格式的 JSON，读取 `width` / `height` 填入对应字段。
   支持 PNG / JPEG / WebP / GIF / HEIC 等主流格式，依赖 macOS 内置 `sips`，无需额外安装。

   **尺寸约束（获取到真实尺寸后进行检查）**：

   | 图层 | 宽度 | 高度 |
   |------|------|------|
   | 海报背景图（`poster.width/height` 及 `images[0]`） | 建议 **750 px** | 不超过 **1500 px** |
   | 海报内其他元素图片（头像、贴纸等） | 不超过 **750 px** | 无硬性限制 |

   若图片尺寸不符合上述约束，**不得私自缩放或裁切**，应向用户说明情况并询问：
   > 您提供的图片尺寸为 {width}×{height}，建议海报宽度为 750 px、高度不超过 1500 px。是否需要更换一张符合尺寸的图片？如果确认使用当前图片，我将按原始尺寸生成海报。

4. **填写其余图层**：在第一张背景图之上叠加文字、头像、二维码等图层。

> 如果用户明确说明不需要海报（只要底部操作面板），则省略 `poster` 字段，退化为纯链接分享模式。

---

## `doSimpleShare`

```ts
action.doSimpleShare(shareInfo, options?)
```

**shareInfo（`ShareProps`）**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `title` | `string` | ✅ | 分享标题 |
| `desc` | `string` | ✅ | 分享描述 |
| `link` | `string` | ✅ | 分享链接 |
| `image` | `string` | ✅ | 分享封面图 URL |
| `poster` | `Poster \| string` | — | 海报配置（有则走 shareImage JSBridge） |
| `dataList` | `ShareDataItem[]` | — | 多份分享数据，优先级高于 `poster` |
| `xhs` | `XHS` | — | 小红书分享扩展配置 |
| `token` / `encryptTid` / `bizType` | `string / number` | — | xhs 海报上传至 CDN 时需要 |
| `sensors` | `ShareImageSensors` | — | 埋点字段（`var_id` 必填时上报 `app_share_click`） |
| `onClose` | `() => void` | — | 面板关闭回调 |

**options（`DoShareOptions`）**

| 字段 | 类型 | 说明 |
|------|------|------|
| `className` | `string` | 额外 CSS 类 |
| `sensors` | `ShareImageSensors \| SharePostersSensors` | 面板级埋点 |
| `showWxShareTips` | `boolean` | 微信 H5 中显示右上角分享提示图（默认 `false`） |
| `token` / `encryptTid` / `bizType` | `string / number` | xhs 海报 CDN 上传凭证 |

**行为说明**

- 无 `poster` / `dataList` → 显示底部滑出的操作面板（微信 / 朋友圈 / 复制等）。
- 有 `poster` / `dataList` → 自动绘制海报并调用 `CoreNative.shareImage`（Native），H5 则弹图片预览弹层。
- 链接自动追加邀请参数（`user.action.getInviteLink`）。
- 有 `sensors.var_id` 且非 Native 海报场景时，**内部自动上报 `app_share_click`**；业务方只需传入 `sensors` 字段，**无需在调用处额外埋点**。

---

## `doMultiPosterShare`

```ts
action.doMultiPosterShare(shareInfo, options?)
```

**shareInfo（`SharePostersProps`）**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `shareTitle` | `string` | ✅ | 分享标题 |
| `shareDescription` | `string` | ✅ | 分享描述 |
| `shareImage` | `string` | ✅ | 分享封面图 URL |
| `shareLink` | `string` | ✅ | 分享链接 |
| `poster` | `Posters` | ✅ | 多海报配置（`blur` + `imageList`） |
| `platforms` | `SharePlatformOverride[]` | — | 分享平台列表 |
| `showQrCode` | `boolean` | — | 是否由客户端拼接二维码 |
| `sensors` | `SharePostersSensors` | — | 埋点（`var_id` / `name` / `type` 等） |
| `webRender` | `React.FC` | — | 站外渲染海报组件 |

**行为说明**

- 走 `hybrid_share_poster` JSBridge，仅在 App 内有效；**业务方自行判断版本兼容性**。
- `poster.imageList[].imageUrl` 中的 base64 前缀会自动去除后传给客户端。

---

## `useRegisterEffect`

```ts
context.useRegisterEffect(shareInfo)
```

- 仅微信 H5 生效（`utils.isWechat`），在 `useEffect` 中调用 `wechat.action.share`。
- `shareInfo.link` 为空时跳过注册。
- `shareInfo` 变化时重新注册（依赖数组为整个对象，建议用 `useMemo` 保持引用稳定）。

---

## 约束与依赖

- 依赖 `window.SoybeanCoreMain`（`native` / 版本号）与 `window.SoybeanCommonMain`。
- `doMultiPosterShare` 要求 App 端支持 `hybrid_share_poster`；版本由业务方判断。
- xhs 小红书分享需 App `>= v5.83.0`（`isEnableXHSShare()`），低版本自动过滤。
- xhs 海报 base64 需 App `>= v6.11.0`，否则需提供 `token` / `encryptTid` 转 CDN 链接。

## 内置埋点说明

> **分享组件已内置点击分享埋点，业务方不需要在调用处再次手动上报。**

| 事件名 | 触发时机 | 条件 |
|--------|----------|------|
| `app_share_click` | 分享面板打开时（`doSimpleShare`） | `sensors.var_id` 非空 且 非 Native 海报场景 |
| `app_share_platform_click` | 用户点击具体分享平台时 | 自动触发，无需业务处理 |

**正确做法**：调用 `doSimpleShare` / `doMultiPosterShare` 时传入 `sensors` 字段即可，组件内部负责在正确时机上报。

```ts
// ✅ 正确：只需传 sensors，不要在外部再 track('app_share_click')
app.share.action.doSimpleShare({
  ...shareInfo,
  sensors: {
    var_id: 'activity_share',
    var_name: '活动分享',
    type_name: '活动',
    source: 'detail_page',
    click_type: 'button',
  },
});

// ❌ 错误：外部额外调用会导致重复上报
sensors.track('app_share_click', { var_id: 'activity_share' });
app.share.action.doSimpleShare({ ... });
```

---

## 常见问题

| 现象 | 排查方向 |
|------|----------|
| 面板不出现 | 确认传入了完整 `ShareProps` 或 `SharePostersProps` |
| 小红书选项缺失 | App 版本低于 `v5.83.0` 或 `xhs.xhsTitle` 为空 |
| 海报绘制失败 | `poster` 字段结构不符合 `Poster` 类型 |
| xhs 海报上传失败 | App 版本低于 `v6.11.0` 时未传 `token` / `encryptTid` |
| 微信分享未生效 | 未调用 `useRegisterEffect` 或 `shareInfo.link` 为空 |
| 埋点重复上报 | 业务方在调用处手动调用了 `track('app_share_click')`，移除即可 |
| 埋点未上报 | `sensors.var_id` 为空；或 Native 海报场景（只上报平台点击） |

## 延伸阅读

- [examples.md](examples.md) — 基础分享、海报分享、多海报、微信注册示例代码
- [reference.md](reference.md) — `ShareProps` / `SharePostersProps` 类型速查
