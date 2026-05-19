# Share 示例（`app.share`）

假定已注入 `window.SoybeanCommonMain.alias`。参数说明见 [SKILL.md](SKILL.md)，类型速查见 [reference.md](reference.md)。

---

## 1. `doSimpleShare` — 基础分享（无海报）

底部滑出操作面板，用户自选微信 / 朋友圈 / 复制链接等平台。

```tsx
const {app} = window.SoybeanCommonMain.alias;

app.share.action.doSimpleShare(
  {
    title: '活动标题',
    desc: '活动描述',
    link: 'https://example.com/activity/123',
    image: 'https://cdn.example.com/cover.jpg',
    timelineTitle: '朋友圈标题',
    timelineDesc: null,
    sensors: {
      var_id: 'activity_share',
      var_name: '活动分享',
      type_name: '活动',
      source: 'detail_page',
      click_type: 'button',
      name: '活动名称',
      type: '活动',
    },
    onClose: () => {
      console.log('分享面板已关闭');
    },
  },
  {
    className: 'my-share-popup',
    showWxShareTips: false,
  },
);
```

---

## 2. `doSimpleShare` — 带单海报（Poster 配置对象）

传入 `poster` 后，组件会先绘制海报再调用 `CoreNative.shareImage` 唤起客户端分享。

**AI 填写此示例前**：必须先获取海报图片的真实宽高，用图片实际尺寸填入下方 `poster.width / height`（画布）和 `images[0].width / height`（图片本身），两组数值保持一致。

```tsx
const {app} = window.SoybeanCommonMain.alias;

app.share.action.doSimpleShare(
  {
    title: '活动标题',
    desc: '邀请你参与',
    link: 'https://example.com/activity/123',
    image: 'https://cdn.example.com/cover.jpg',
    timelineTitle: null,
    timelineDesc: null,
    poster: {
      width: 750,
      height: 1334,
      backgroundColor: '#FFFFFF',
      pixelRatio: 1,
      images: [
        {
          url: 'https://cdn.example.com/poster-bg.jpg',
          x: 0,
          y: 0,
          width: 750,
          height: 1334,
          zIndex: 0,
        },
        {
          url: 'https://cdn.example.com/avatar.jpg',
          x: 30,
          y: 60,
          width: 80,
          height: 80,
          borderRadius: 40,
          zIndex: 1,
        },
      ],
      texts: [
        {
          x: 30,
          y: 200,
          text: '活动标题',
          fontSize: 36,
          color: '#333333',
          fontWeight: 'bold',
          textAlign: 'left',
          baseLine: 'top',
          width: 690,
          lineNum: 2,
          lineHeight: 48,
          zIndex: 2,
        },
      ],
      blocks: [
        {
          x: 30,
          y: 1050,
          width: 200,
          height: 48,
          borderRadius: 24,
          paddingLeft: 16,
          paddingRight: 16,
          createLinearGradient: {
            x0: 0, y0: 0,
            x1: 0, y1: 48,
            colorStop: [
              {stop: 0, color: '#FFE5F1'},
              {stop: 1, color: '#FFFFFF'},
            ],
          },
          topLeft: 24, topRight: 24, bottomLeft: 24, bottomRight: 24,
          text: {
            text: '立即参与',
            fontSize: 24,
            color: '#FFFFFF',
            textAlign: 'center',
            baseLine: 'middle',
          },
          zIndex: 3,
        },
      ],
      lines: [
        {
          startX: 30,
          startY: 980,
          endX: 720,
          endY: 980,
          width: 1,
          color: '#EEEEEE',
          zIndex: 1,
        },
      ],
      qrcode: [
        {
          text: 'https://example.com/activity/123',
          width: 120,
          height: 120,
          left: 315,
          top: 1100,
          padding: 4,
          background: '#ffffffff',
          foreground: '#000000ff',
          errorCorrectionLevel: 'L',
          zIndex: 4,
        },
      ],
    },
    xhs: {
      xhsTitle: '小红书发布标题',
      xhsSubTitle: '小红书发布副标题',
      xhsImageUrls: [],
      poster: {
        width: 750,
        height: 1334,
        backgroundColor: '#FFF',
        images: [],
        qrcode: [],
      },
    },
    token: 'your-upload-token',
    encryptTid: 'your-encrypt-tid',
    bizType: 8,
    sensors: {
      var_id: 'poster_share',
      var_name: '海报分享',
      type_name: '活动',
      source: 'detail_page',
      click_type: 'button',
    },
    onClose: () => {},
  },
  {
    showWxShareTips: false,
  },
);
```

---

## 3. `doSimpleShare` — 多数据海报（dataList）

`dataList` 优先级高于 `poster`，适用于同一次分享携带多个内容项（各有独立标题、链接、海报）。

```tsx
const {app} = window.SoybeanCommonMain.alias;

app.share.action.doSimpleShare(
  {
    title: '书单推荐',
    desc: '发现好书',
    link: 'https://example.com/booklist/1',
    image: 'https://cdn.example.com/cover.jpg',
    timelineTitle: null,
    timelineDesc: null,
    dataList: [
      {
        title: '书目一标题',
        desc: '书目一简介',
        link: 'https://example.com/book/1',
        image: 'https://cdn.example.com/book1.jpg',
        poster: {
          width: 750,
          height: 1334,
          backgroundColor: '#FFFFFF',
          images: [{url: 'https://cdn.example.com/book1-bg.jpg', x: 0, y: 0, width: 750, height: 1334}],
          texts: [{x: 30, y: 200, text: '书目一标题', fontSize: 36, color: '#333'}],
          blocks: [],
          lines: [],
          qrcode: [{text: 'https://example.com/book/1', width: 120, height: 120, left: 315, top: 1100, padding: 4}],
        },
        var_id: 'book_1',
        var_name: '书目一',
      },
      {
        title: '书目二标题',
        desc: '书目二简介',
        link: 'https://example.com/book/2',
        image: 'https://cdn.example.com/book2.jpg',
        poster: {
          width: 750,
          height: 1334,
          backgroundColor: '#FFFFFF',
          images: [{url: 'https://cdn.example.com/book2-bg.jpg', x: 0, y: 0, width: 750, height: 1334}],
          qrcode: [{text: 'https://example.com/book/2', width: 120, height: 120, left: 315, top: 1100, padding: 4}],
        },
      },
    ],
    sensors: {
      var_id: 'booklist_share',
      var_name: '书单分享',
      type_name: '书单',
      source: 'booklist_page',
      click_type: 'button',
    },
    onClose: () => {},
  },
  {
    className: 'my-share-popup',
    showWxShareTips: false,
  },
);
```

---

## 4. `doMultiPosterShare` — 多海报分享

调用 `hybrid_share_poster` JSBridge，**仅 App 内有效**，版本兼容由业务方自行判断。

```tsx
const {app} = window.SoybeanCommonMain.alias;

app.share.action.doMultiPosterShare(
  {
    shareTitle: '书单推荐',
    shareDescription: '发现好书',
    shareImage: 'https://cdn.example.com/cover.jpg',
    shareLink: 'https://example.com/booklist/456',
    showQrCode: true,
    poster: {
      blur: 0,
      imageList: [
        {
          posterId: 1,
          imageUrl: 'https://cdn.example.com/poster1.jpg',
          mainTitle: '书单主标题',
          subTitle: '副标题',
          codeUrl: 'https://example.com/booklist/456',
          logoUrl: 'https://cdn.example.com/logo.png',
          xhsTitle: '小红书笔记标题',
          xhsSubTitle: '小红书笔记副标题',
          xhsImageUrls: ['https://cdn.example.com/xhs1.jpg'],
        },
        {
          posterId: 2,
          imageUrl: 'https://cdn.example.com/poster2.jpg',
        },
      ],
    },
    platforms: ['wechatSession', 'timeLine', 'savePhoto', 'xiaohongshu', 'shareLink', 'copyLink'],
    sensors: {
      var_id: 'booklist_poster_share',
      name: '书单海报分享',
      type: '书单',
      source: 'booklist_page',
      click_type: 'button',
    },
    onClose: () => {},
  },
  {
    className: 'my-poster-popup',
    showWxShareTips: false,
    sensors: {
      var_id: 'booklist_poster_share',
      name: '书单海报分享',
      type: '书单',
      source: 'booklist_page',
      click_type: 'button',
    },
  },
);
```

---

## 5. `useRegisterEffect` — 微信 H5 分享注册

在微信浏览器页面中调用，让右上角「分享给朋友」/ 「分享到朋友圈」携带自定义内容。非微信环境自动跳过。

```tsx
const {app} = window.SoybeanCommonMain.alias;

function ActivityPage({activity}: {activity: Activity}) {
  const shareInfo = useMemo(() => ({
    title: activity.title,
    desc: activity.desc,
    link: `https://example.com/activity/${activity.id}`,
    image: activity.coverImage,
    timelineTitle: activity.timelineTitle ?? null,
    timelineDesc: activity.timelineDesc ?? null,
  }), [activity]);

  app.share.context.useRegisterEffect(shareInfo);

  return <div>{activity.title}</div>;
}
```
