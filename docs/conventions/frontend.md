# Frontend Conventions (`front/`)

> 适用范围：`scaffolding-python/front/src/**`
> 受众：人类开发者 + LLM 代码生成工具

核心原则：**单一 HTTP 入口 + 状态分层 + 路径别名 + 零 lint warning**。违反下面任何一条会被 `scripts/guard-conventions.sh` 在 pre-commit 里拦住。

---

## 1. HTTP 只走 `@/api/http`

- 所有 axios 调用 **必须** 通过 `@/api/http` 的默认导出。拦截器负责：注入 `Authorization: Bearer <token>`、按 `Result` 信封解包成业务数据、401 自动清登录态并跳 `/login`、403/其它做消息提示。
- **禁止** 在任何业务文件里 `import axios from 'axios'`（只有 `@/api/http.ts` 可以）。
- **禁止** 直接 `fetch('/api/...')` 或 `fetch('http://localhost:8080/...')` 调后端。
- baseURL 组装由 `http.ts` 统一决定（`VITE_API_PREFIX` + `VITE_API_BASE_URL`）；业务里**永远**写相对 `/xxx`，不要自己拼前缀。
- 需要非 axios 的场景（`<a href>`、SSE、`EventSource`、大文件下载）用 `withApiPrefix(path)` 生成绝对路径。
- 新接口在 `src/api/*.ts` 加一个函数（一个资源一个文件），再由 page / hook 调用。

### ✅

```ts
// src/api/user.ts
import http from '@/api/http'
export const fetchMe = () => http.get<UserResponse>('/users/me')

// src/pages/Home.tsx
const { data } = useQuery({ queryKey: ['me'], queryFn: fetchMe })
```

### ❌

```ts
import axios from 'axios'                                  // ❌ guard 会拦
const res = await axios.get('http://localhost:8080/api/users/me')

await fetch('/api/users/me', {                             // ❌ guard 会拦
  headers: { Authorization: `Bearer ${token}` },
})
```

---

## 2. 状态分层

| 场景 | 方案 | 放哪 |
| --- | --- | --- |
| 组件内部 UI 状态 | `useState` / `useReducer` | 组件里 |
| 跨组件全局状态（登录态、主题、语言…） | Zustand | `src/store/*.ts`，一个域一个 store |
| 服务端数据 / 缓存 / 轮询 / 乐观更新 | TanStack Query | 直接在 page / hook 里用 `useQuery` / `useMutation` |

- **不要** 把远端数据塞进 Zustand —— 会丢失 Query 的缓存失效、自动 refetch、乐观更新能力。
- **不要** 把 UI 全局态（主题、语言）塞 Query —— 它不是 "远端资源"。
- Auth 是例外：**token** 进 Zustand（持久化 + 同步拦截器用），**当前用户信息** 走 Query（`['me']`）。

### ✅

```ts
// store/auth.ts
export const useAuthStore = create<AuthState>()(
  persist(set => ({ token: null, setToken: t => set({ token: t }), logout: () => set({ token: null }) }),
    { name: 'auth' }),
)

// pages/UserList.tsx
const { data } = useQuery({ queryKey: ['users', page], queryFn: () => fetchUsers(page) })
```

### ❌

```ts
// 把远端列表塞 zustand，需要手动失效 —— 容易漏
const useUsers = create(set => ({
  users: [],
  load: async () => set({ users: await fetchUsers() }),
}))
```

---

## 3. 路径别名 `@/`

- `@/` 固定指向 `front/src/`（见 `tsconfig.json` + `vite.config.ts`，已配好，**别动**）。
- **禁止** `../../../components/xxx` 两层或以上的相对爬楼 —— `guard-conventions.sh` 会拦 `from '../../'` 起的 import。
- **禁止** 新增其它别名（如 `~components`、`#utils`），保持只有 `@/`。
- 一层相对（`./schema`、`./components/XxxForm`）可以，用于页面目录内部。

### ✅

```ts
import { Layout } from '@/components/Layout'
import { useAuthStore } from '@/store/auth'
import { LoginForm } from './components/LoginForm'        // 页面目录内部
```

### ❌

```ts
import { Layout } from '../../components/Layout'          // ❌ 爬楼
import { Layout } from '~components/Layout'               // ❌ 新别名
```

---

## 4. 表单

- 校验：`react-hook-form` + `zod`（`@hookform/resolvers/zod`）。
- schema 放在 `src/pages/<Page>/schema.ts` 或组件同目录。
- **不要** 同时用 AntD `Form` 的 `rules` 再写一遍 zod schema 表达过的规则；AntD `Form` 只负责布局。

### ✅

```ts
const schema = z.object({
  username: z.string().min(3).max(32),
  password: z.string().min(6),
})
const { register, handleSubmit, formState: { errors } } = useForm({
  resolver: zodResolver(schema),
})
```

---

## 5. UI / 图标 / i18n

- **AntD 5** 为主组件库；新组件库（shadcn、MUI、Chakra 等）要先评审。
- **图标**：统一 `lucide-react`；禁止混用 `@ant-design/icons` 和 `react-icons`（AntD 组件自身带的图标按钮除外）。
- **文案**：用 `react-i18next`；面向用户的中文**不要**硬编码在 JSX / error message 里，统一在 `src/locales/*.json` 或 i18n resource 里。

---

## 6. 低端机器兼容性

目标用户可能使用低端设备或旧版 WebView / 浏览器，新增前端代码默认按“低配置可用、渐进增强”处理：

- **开发 API 先查兼容性**：使用较新的 Web API 前，先确认目标运行环境支持情况；不确定时不要直接上生产路径。
- **禁用未经兜底的高级浏览器 API**：`ResizeObserver`、`IntersectionObserver`、`AbortController`、`requestIdleCallback`、`structuredClone`、`crypto.randomUUID`、Clipboard、Web Worker、BroadcastChannel 等能力必须先做特性检测，缺失时提供降级、polyfill 或安全跳过。
- **语法保持构建可降级**：业务代码避免依赖运行时才支持的新语法 / 原型方法；使用 `Array.prototype.at`、`Object.groupBy`、`Promise.withResolvers`、`toSorted` / `toSpliced`、`String.prototype.replaceAll` 等新 API 前，确认已有 polyfill 或改用兼容写法。
- **性能优先轻量实现**：低端机上避免大列表一次性渲染、频繁深拷贝 / JSON 序列化、滚动 / resize 高频 setState、首屏同步重计算；必要时分页、虚拟列表、节流 / 防抖、懒加载。
- **动效与视觉效果可降级**：复杂动画、毛玻璃、阴影叠加、滤镜、超大图片 / SVG 只能作为增强效果；基础信息展示和核心操作不能依赖这些效果。
- **CSS 写法优先保守兼容**：默认不要使用低端机 / 旧 WebView 兼容性差的 CSS 能力，例如 flex / grid 的 `gap`、`position: sticky`、`backdrop-filter`、复杂 `filter`、`aspect-ratio`、`content-visibility`、容器查询、嵌套 CSS、`:has()` 等；必须使用时先确认目标环境支持，并提供 margin / padding / 固定尺寸等兼容兜底。
- **布局间距不要依赖 `gap`**：横纵列表、按钮组、表单项间距优先用子元素 `margin`、父容器 padding 或 AntD 兼容能力；不要把 `gap` 当成默认方案。
- **兼容逻辑集中封装**：需要 polyfill、特性检测或降级分支时，优先放在 `src/utils/` 或专用 hook，页面里只调用封装后的能力，避免散落判断。
- **新增依赖要谨慎**：不要为了一个新 API 兼容引入重型 polyfill 包；优先小函数、已有依赖或按需 polyfill。

### ✅

```ts
const id = typeof crypto !== 'undefined' && 'randomUUID' in crypto
  ? crypto.randomUUID()
  : `${Date.now()}-${Math.random().toString(36).slice(2)}`

const first = list.length > 0 ? list[0] : undefined
```

```css
.toolbar > * + * {
  margin-left: 8px;
}
```

### ❌

```ts
const id = crypto.randomUUID()                         // ❌ 旧 WebView 可能不存在
const first = list.at(0)                               // ❌ 未确认 polyfill 前不要用
window.requestIdleCallback(() => preload())            // ❌ 未做特性检测
```

```css
.toolbar {
  display: flex;
  gap: 8px;                                           /* ❌ 旧 WebView / 低端机兼容风险 */
}
```

---

## 7. ESLint / Prettier / TypeScript

| 工具 | 命令 | 门槛 |
| --- | --- | --- |
| ESLint | `npm run lint`（= `--max-warnings 0`） | **零 warning** |
| TypeScript | `npm run type-check`（`tsc --noEmit`） | **零错误**，禁 `any` |
| Prettier | `npm run format` | 写回 `src/**` |
| 构建 | `npm run build`（= `tsc -b && vite build`） | 必须过 |

- **禁止** `any` 作为显式注解（`const x: any = ...`、`(x: any) => ...`）—— `guard-conventions.sh` 会拦。过渡期用 `unknown` + 类型守卫；第三方库类型缺失时优先补 `.d.ts`。
- **禁止** 文件首 `/* eslint-disable */` 整文件禁用；需要局部禁用时写 `// eslint-disable-next-line <rule> -- <reason>`，理由必填。
- CI 跑 `type-check → lint → build`，任何一步失败都会红。
- 一个未使用的 import 也会 fail CI —— 提交前跑一次 `npm run lint`。

### ✅

```ts
const data = res.data as UserResponse                      // 明确类型
// eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: run once on mount
useEffect(() => { init() }, [])
```

### ❌

```ts
/* eslint-disable */                                       // ❌ 整文件禁
const data: any = res.data                                 // ❌ guard 会拦
```

---

## 8. 路由 & 权限

- 路由集中在 `src/router/index.tsx`（`createBrowserRouter` / `RouterProvider`）。
- 需要登录的页面统一套 `ProtectedRoute`（`src/router/ProtectedRoute.tsx`），**不要**在每个组件自己判 token 重定向。
- 404 走 `pages/NotFound.tsx`，不要每个模块自己写。
- 新增受保护页 = 在 `router/index.tsx` 加一个 `ProtectedRoute` 子节点，顺便决定是否需要 layout wrap。

---

## 9. 目录 & 命名

| 目录 | 放什么 | 命名 |
| --- | --- | --- |
| `src/api/` | `http.ts`（唯一 axios 实例） + 每个资源一个 `.ts`（`auth.ts`、`user.ts`） + 汇总 `index.ts` | camelCase |
| `src/components/` | **通用** 组件（Layout、Empty、ErrorBoundary）。页面私有组件放 `pages/<Page>/components/` | PascalCase |
| `src/pages/` | 路由页面；文件夹 = 页面，文件 = 默认导出组件 | PascalCase |
| `src/hooks/` | 通用 hooks | `useXxx` |
| `src/store/` | Zustand store，一个域一个文件 | `xxx.ts`，导出 `useXxxStore` |
| `src/types/` | 与后端 Schema 对齐的 TS 类型（`UserResponse`、`ApiResult<T>`…） | PascalCase |
| `src/utils/` | **纯函数**工具，无 React 依赖 | camelCase |
| `src/router/` | `index.tsx`、`ProtectedRoute.tsx` | 固定 |

- 一个文件一个导出**组件**（页面）；工具函数可以多导出。
- 带 React 依赖的复用逻辑 → `hooks/`，不要丢 `utils/`。

---

## 10. 环境变量

仅暴露 `VITE_*` 前缀的变量；业务从 `import.meta.env.VITE_*` 读。

| 变量 | 用途 | 默认 |
| --- | --- | --- |
| `VITE_API_BASE_URL` | axios `baseURL` 基础段 | `/api` |
| `VITE_API_PREFIX` | 业务网关统一前缀（如 `/scaffold`）。本地通常为空；生产由 nginx 反代去前缀后打到后端 | `""` |
| `VITE_API_TARGET` | Vite dev server 的 proxy 目标 | `http://localhost:8080` |
| `VITE_APP_TITLE` | HTML title | 项目名 |

env 文件：`.env.development`、`.env.production`（受 `VITE_` 白名单约束；**不要**把密钥放这里，浏览器能读到）。

---

## 11. 与后端 Schema 对齐

- 后端返回 `{ code, message, data }`；`http.ts` 已把 `code === 200` 的 `res.data` 展开成业务数据，页面里直接用 `res.data: UserResponse`。
- TS 类型写在 `src/types/`，字段名必须跟后端 `schemas/*.py` 的 `UserResponseSchema` 对齐（snake_case 是否转 camelCase 由当前仓库约定决定 —— 目前后端原样 `created_at` / `updated_at`，TS 侧也用 `created_at`，**不要**两边不一致自己悄悄转）。
- 后端改了字段、加了字段 → TS 类型必须跟着改，否则 `tsc` 会直接红。
