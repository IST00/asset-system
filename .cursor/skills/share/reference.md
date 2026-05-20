# Share 参考（`app.share`）

完整类型定义与平台枚举速查，用于编写时对照。行为说明见 [SKILL.md](SKILL.md)，代码示例见 [examples.md](examples.md)。

---

## 类型速查

### `ShareProps`

```ts
type ShareProps = {
  title: string;                     // 微信分享卡片标题
  desc: string;                      // 微信分享卡片描述
  link: string;                      // 分享跳转链接（自动追加邀请参数）
  image: string;                     // 分享卡片封面图 URL
  timelineTitle?: string | null;     // 朋友圈独立标题；null 则同 title
  timelineDesc?: string | null;      // 朋友圈独立描述；null 则同 desc
  poster?: Poster | string;          // 单个海报（配置对象或已有图片 URL）
  dataList?: ShareDataItem[];        // 多份数据，优先级高于 poster
  xhs?: XHS;                        // 小红书扩展配置（需 App >= v5.83.0）
  sensors?: ShareImageSensors;      // 埋点参数
  onClose?: () => void;             // 面板关闭后的回调
  token?: string;                   // xhs 海报 base64 转 CDN 的上传凭证（仅 App < v6.11.0 时需要）
  encryptTid?: string;              // 加密业务 ID
  bizType?: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;  // 业务类型枚举
};
```

### `SharePostersProps`

```ts
type SharePostersProps = {
  shareTitle: string;                     // 分享卡片标题
  shareDescription: string;              // 分享卡片描述
  shareImage: string;                    // 分享卡片封面图 URL
  shareLink: string;                     // 分享跳转链接
  poster: Posters;                       // 多海报配置
  platforms?: SharePlatformOverride[];   // 指定展示的分享平台，不传则由客户端决定默认列表
  showQrCode?: boolean;                  // true 表示由客户端在海报上拼接二维码
  sensors?: SharePostersSensors;         // 埋点参数
  webRender?: React.FC<any>;             // 站外渲染由业务实现
  onClose?: () => void;                  // 面板关闭回调
};
```

### `DoShareOptions`

```ts
type DoShareOptions = {
  className?: string;                                 // 给弹层追加的 CSS 类名
  sensors?: ShareImageSensors | SharePostersSensors; // 覆盖 shareInfo.sensors（通常保持一致）
  showWxShareTips?: boolean;                         // true 时在微信浏览器内显示右上角引导提示图
  token?: string;                                    // xhs 海报 base64 转 CDN 的上传凭证（仅 App < v6.11.0 时需要）
  encryptTid?: string;                               // 加密业务 ID
  bizType?: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;         // 业务类型枚举
};
```

### `Poster`（单海报配置）

```ts
type Poster = {
  width: number;             // 画布宽度（px）
  height: number;            // 画布高度（px）
  backgroundColor: string;   // 画布背景色
  pixelRatio?: number;       // 像素比率，默认 1

  images?: PosterImage[];    // 图片图层
  texts?: PosterText[];      // 文字图层
  blocks?: PosterBlock[];    // 矩形块图层
  lines?: PosterLine[];      // 线条图层
  qrcode?: PosterQRCode[];   // 二维码图层
  // 各图层按 zIndex 升序渲染，zIndex 相同时按数组顺序
};

// 图片图层
type PosterImage = {
  url: string;               // 图片 URL（CDN 或 base64）
  x: number;                 // 左上角 x 坐标（px）
  y: number;                 // 左上角 y 坐标（px）
  width: number;             // 绘制宽度（px）
  height: number;            // 绘制高度（px）
  zIndex?: number;           // 层叠顺序，默认按数组下标
  borderRadius?: number;     // 圆角半径（px），默认 0
  borderWidth?: number;      // 边框宽度（px）
  borderColor?: string;      // 边框颜色
  skewX?: number;            // X 轴倾斜角度（deg）
  skewY?: number;            // Y 轴倾斜角度（deg）
};

// 文字图层
type PosterText = {
  x: number;                              // x 坐标（px）
  y: number;                              // y 坐标（px）
  text: string | PosterTextSegment[];     // 文字；数组时各段独立样式（富文本）
  fontSize: number;                       // 字号（px）
  color?: string;                         // 文字颜色
  fontWeight?: 'normal' | 'bold';         // 默认 'normal'
  fontStyle?: 'normal' | 'italic';        // 默认 'normal'
  fontFamily?: string;                    // 默认 'sans-serif'
  textAlign?: 'left' | 'center' | 'right'; // 默认 'left'
  baseLine?: 'top' | 'middle' | 'bottom'; // 基线对齐方式
  width?: number;                         // 文字区域宽度（px），超出按 lineNum 截断
  lineNum?: number;                       // 最大行数，超出末尾补 '...'，默认 1
  lineHeight?: number;                    // 行高（px），默认取 fontSize
  opacity?: number;                       // 透明度 0-1，默认 1
  textDecoration?: 'none' | 'line-through'; // 默认 'none'
  rotate?: number;                        // 旋转角度（deg），默认 0
  zIndex?: number;
};

// 富文本段（text 为数组时每项的格式）
type PosterTextSegment = {
  text: string;                    // 文字内容
  fontSize: number;                // 字号（px）
  color?: string;                  // 文字颜色
  fontWeight?: 'normal' | 'bold';  // 字重
  marginLeft?: number;             // 段前间距（px）
  marginRight?: number;            // 段后间距（px）
};

// 矩形块图层
type PosterBlock = {
  x: number;                   // x 坐标（px）
  y: number;                   // y 坐标（px）
  height: number;              // 高度（px）
  width?: number;              // 宽度（px）；有 text 时由文字宽度 + padding 决定
  backgroundColor?: string;    // 背景色
  borderRadius?: number;       // 圆角半径（px），默认 0
  borderWidth?: number;        // 边框宽度（px）
  borderColor?: string;        // 边框颜色
  paddingLeft?: number;        // 内左边距（px），默认 0
  paddingRight?: number;       // 内右边距（px），默认 0
  opacity?: number;            // 透明度 0-1，默认 1
  createLinearGradient?: {     // 存在时 backgroundColor/borderWidth/borderColor 失效
    x0: number; y0: number;    // 渐变起点（相对块自身）
    x1: number; y1: number;    // 渐变终点
    colorStop: Array<{stop: number; color: string}>;
  };
  topLeft?: number;            // 左上角圆角（配合 createLinearGradient）
  topRight?: number;           // 右上角圆角
  bottomLeft?: number;         // 左下角圆角
  bottomRight?: number;        // 右下角圆角
  text?: PosterText;           // 块内嵌文字
  zIndex?: number;
};

// 线条图层
type PosterLine = {
  startX: number;   // 起始 x（px）
  startY: number;   // 起始 y（px）
  endX: number;     // 终结 x（px）
  endY: number;     // 终结 y（px）
  width: number;    // 线宽（px）
  color?: string;   // 线颜色
  zIndex?: number;
};

// 二维码图层
type PosterQRCode = {
  text: string;                           // 二维码编码内容（链接或文字）
  width: number;                          // 宽度（px）
  height: number;                         // 高度（px）
  left: number;                           // 距左边距（px）
  top: number;                            // 距上边距（px）
  padding?: number;                       // 边距（px），默认 5
  background?: string;                    // 背景色（RGBA），默认 '#ffffffff'
  foreground?: string;                    // 码块颜色（RGBA），默认 '#000000ff'
  errorCorrectionLevel?: 'L'|'M'|'Q'|'H'; // 纠错等级，默认 'L'
  zIndex?: number;
};
```

### `Posters`（多海报配置）

```ts
type Posters = {
  blur: 0 | 1;              // 0: 不模糊；1: 高斯模糊背景
  imageList: PosterListItemProps[];
};

type PosterListItemProps = {
  posterId: number;                  // 海报唯一 ID
  imageUrl: Poster | string;         // 海报图片 URL 或 Poster 配置对象
  mainTitle?: string;                // 客户端生成二维码时附带的主标题
  subTitle?: string;                 // 客户端生成二维码时附带的副标题
  codeUrl?: string;                  // 二维码跳转链接
  logoUrl?: string;                  // 二维码中央 Logo URL
  xhsTitle?: string;                 // 小红书分享时使用的标题
  xhsSubTitle?: string;              // 小红书分享时使用的副标题
  xhsImageUrls?: string[];           // 小红书图片 URL 列表（目前只支持链接，客户端预留 base64 支持）
};
```

### `ShareDataItem`（多数据分享项）

```ts
type ShareDataItem = {
  title: string;                     // 该项分享标题
  desc: string;                      // 该项分享描述
  link: string;                      // 该项分享链接（自动追加邀请参数）
  image: string;                     // 该项分享封面图
  poster: Poster;                    // 该项海报配置（完整 Poster 结构）
  var_id?: string;                   // 用于各项埋点区分
  var_name?: string;                 // 用于各项埋点区分
};
```

### `XHS`（小红书配置）

```ts
type XHS = {
  xhsImageUrls: string[];            // 已有图片 URL 列表（与 poster 二选一；优先 poster）
  xhsTitle: string;                  // 小红书笔记标题
  xhsSubTitle: string;               // 小红书笔记副标题
  poster?: Poster;                   // 小红书专属海报配置（与 ShareProps.poster 独立绘制）
};
```

### `ShareImageSensors`

```ts
type ShareImageSensors = {
  var_id: string;     // 埋点资源 ID；空字符串则不上报 app_share_click
  name?: string;      // 冗余 name 字段（优先级低于 var_name）
  type?: string;      // 冗余 type 字段（优先级低于 type_name）
  var_name: string;   // 资源名称
  type_name: string;  // 资源类型名称
  source: string;     // 来源页面标识
  click_type: string; // 点击方式（button / banner / card 等）
};
```

### `SharePostersSensors`

```ts
type SharePostersSensors = {
  var_id: string;     // 埋点资源 ID
  name: string;       // 资源名称
  type: string;       // 资源类型
  source: string;     // 来源页面标识
  click_type: string; // 点击方式
};
```

---

## 埋点事件

> **分享组件内置了点击分享埋点，业务方传入 `sensors` 字段即可，不需要在调用处手动上报 `app_share_click`，否则会重复计数。**

| 事件名 | 触发时机 | 触发方 |
|--------|----------|--------|
| `app_share_click` | `doSimpleShare` 面板打开时（有 `sensors.var_id`，非 Native 海报） | 组件内部自动上报 |
| `app_share_platform_click` | 用户点击具体分享平台时 | 组件内部自动上报 |
