# Asset Dashboard Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable light-theme asset-system application shell and responsive dashboard that follows the supplied prototypes while remaining easy to restyle centrally.

**Architecture:** Central theme tokens and AntD configuration define all shared visual decisions. A configuration-driven `AppShell` owns desktop and mobile navigation, while dashboard-specific typed data and selectors stay inside `features/dashboard`; reusable visual primitives stay in `components/ui`.

**Tech Stack:** React 18, TypeScript, Vite 5, Ant Design 5, Lucide React, React Router 6, React Query 5, i18next, Node.js 22 built-in test runner.

---

## File map

**Create:**

- `front/src/theme/tokens.ts` — semantic design tokens and AntD theme configuration input.
- `front/src/theme/index.ts` — theme exports.
- `front/src/i18n/index.ts` — Simplified Chinese i18next initialization.
- `front/src/i18n/zhCN.ts` — all new user-facing shell and dashboard copy.
- `front/src/config/navigationModel.ts` — framework-free navigation types and selectors.
- `front/src/config/navigationModel.test.ts` — Node tests for desktop/mobile and permission filtering.
- `front/src/config/navigation.ts` — concrete navigation entries with Lucide icon identifiers.
- `front/src/layouts/AppShell/index.tsx` — shared responsive application shell.
- `front/src/layouts/AppShell/AppShell.css` — shell, desktop rail, drawer and mobile bottom-bar styles.
- `front/src/components/ui/PageHeader.tsx` — shared page heading and supporting text.
- `front/src/components/ui/MetricCard.tsx` — shared metric presentation.
- `front/src/components/ui/SectionPanel.tsx` — shared titled content region.
- `front/src/components/ui/StatePanel.tsx` — shared empty/error presentation.
- `front/src/components/ui/ui.css` — reusable UI primitive styles.
- `front/src/features/dashboard/types.ts` — dashboard data contracts.
- `front/src/features/dashboard/dashboardModel.ts` — framework-free derived dashboard values.
- `front/src/features/dashboard/dashboardModel.test.ts` — Node tests for dashboard derived values.
- `front/src/features/dashboard/dashboardData.ts` — typed, isolated demo data.
- `front/src/features/dashboard/Dashboard.tsx` — dashboard page composition.
- `front/src/features/dashboard/Dashboard.css` — responsive dashboard layout.

**Modify:**

- `front/package.json` — add a Node 22 built-in `test` script only; do not add dependencies.
- `front/src/main.tsx` — initialize i18n and pass the centralized AntD theme.
- `front/src/router/index.tsx` — use `AppShell` and lazy-load the dashboard.
- `front/src/pages/Home.tsx` — reduce to the route-level dashboard export.
- `front/src/index.css` — apply global tokens, reset and base typography.
- `front/src/types/index.ts` — add the optional permission list supplied by future auth responses.

**Delete:**

- `front/src/components/Layout.tsx` — superseded by `layouts/AppShell`.

## Task 1: Add testable dashboard and navigation models

**Files:**

- Create: `front/src/config/navigationModel.test.ts`
- Create: `front/src/config/navigationModel.ts`
- Create: `front/src/features/dashboard/dashboardModel.test.ts`
- Create: `front/src/features/dashboard/dashboardModel.ts`
- Create: `front/src/features/dashboard/types.ts`
- Modify: `front/package.json`

- [ ] **Step 1: Add the Node test command**

Add this script without changing dependencies:

```json
"test": "node --experimental-strip-types --test src/config/navigationModel.test.ts src/features/dashboard/dashboardModel.test.ts"
```

- [ ] **Step 2: Write failing navigation tests**

Test that permission-protected entries are hidden, disabled entries remain visible on desktop, and mobile navigation contains only its four explicit entries:

```ts
import assert from 'node:assert/strict'
import test from 'node:test'
import { filterNavigation } from './navigationModel.ts'
import type { NavigationEntry } from './navigationModel.ts'

const entries: NavigationEntry[] = [
  { key: 'home', labelKey: 'nav.home', path: '/home', icon: 'home', mobile: true },
  { key: 'assets', labelKey: 'nav.assets', path: '/assets', icon: 'package', mobile: true },
  { key: 'inventory', labelKey: 'nav.inventory', path: '/inventory', icon: 'scan', mobile: true },
  { key: 'profile', labelKey: 'nav.profile', path: '/profile', icon: 'user', mobile: true },
  { key: 'permissions', labelKey: 'nav.permissions', path: '/permissions', icon: 'shield', permission: 'role:view' },
]

test('filters protected navigation by permission', () => {
  assert.deepEqual(filterNavigation(entries, new Set()).map((item) => item.key), ['home', 'assets', 'inventory', 'profile'])
  assert.equal(filterNavigation(entries, new Set(['role:view'])).length, 5)
})

test('selects the four explicit mobile destinations', () => {
  assert.deepEqual(filterNavigation(entries, new Set(), true).map((item) => item.key), ['home', 'assets', 'inventory', 'profile'])
})
```

- [ ] **Step 3: Write failing dashboard model tests**

Test progress clamping, visible metric selection and issue totals:

```ts
import assert from 'node:assert/strict'
import test from 'node:test'
import { calculateProgress, countActionableIssues, selectPrimaryMetrics } from './dashboardModel.ts'
import type { DashboardOverview } from './types.ts'

const overview: DashboardOverview = {
  metrics: { total: 156, idle: 42, inUse: 98, repairing: 8, scrapped: 5 },
  issues: { pendingApprovals: 4, inventoryExceptions: 3, incompleteAssets: 12, departedOwnerAssets: 2 },
  inventory: { taskName: '2026 Q3 资产盘点', checked: 90, total: 120, exceptions: 3 },
  categories: [],
  monthlyChanges: [],
}

test('derives stable dashboard values', () => {
  assert.equal(calculateProgress(overview.inventory), 75)
  assert.equal(countActionableIssues(overview.issues), 21)
  assert.deepEqual(selectPrimaryMetrics(overview.metrics).map((metric) => metric.key), ['total', 'idle', 'inUse', 'repairing'])
})

test('clamps invalid progress values', () => {
  assert.equal(calculateProgress({ taskName: 'empty', checked: 5, total: 0, exceptions: 0 }), 0)
  assert.equal(calculateProgress({ taskName: 'overflow', checked: 20, total: 10, exceptions: 0 }), 100)
})
```

- [ ] **Step 4: Run tests and confirm the expected failure**

Run: `cd front && npm test`

Expected: FAIL because `navigationModel.ts`, `dashboardModel.ts`, and `types.ts` do not exist.

- [ ] **Step 5: Implement the minimal framework-free models**

Define `NavigationEntry`, `filterNavigation`, the dashboard interfaces, `calculateProgress`, `countActionableIssues`, and `selectPrimaryMetrics`. Keep icon values as string identifiers so Node tests never import TSX or React.

- [ ] **Step 6: Run model tests**

Run: `cd front && npm test`

Expected: 4 tests pass with zero failures.

- [ ] **Step 7: Commit the models**

```bash
git add front/package.json front/src/config/navigationModel.ts front/src/config/navigationModel.test.ts front/src/features/dashboard/types.ts front/src/features/dashboard/dashboardModel.ts front/src/features/dashboard/dashboardModel.test.ts
git commit -m "test(front): add dashboard view models"
```

## Task 2: Centralize theme and Simplified Chinese copy

**Files:**

- Create: `front/src/theme/tokens.ts`
- Create: `front/src/theme/index.ts`
- Create: `front/src/i18n/index.ts`
- Create: `front/src/i18n/zhCN.ts`
- Modify: `front/src/main.tsx`
- Modify: `front/src/index.css`

- [ ] **Step 1: Define semantic tokens**

Create a typed token object for brand, semantic colors, backgrounds, borders, text, radii, spacing, navigation width, content width and breakpoints. Export an AntD `ThemeConfig` derived from the same values:

```ts
export const designTokens = {
  color: {
    brand: '#2563eb',
    brandHover: '#1d4ed8',
    canvas: '#f5f7fb',
    surface: '#ffffff',
    border: '#e6eaf0',
    text: '#172033',
    textMuted: '#667085',
    success: '#169c68',
    warning: '#d97706',
    danger: '#dc3545',
  },
  radius: { small: 8, medium: 12, large: 16 },
  layout: { railWidth: 72, maxContentWidth: 1440, mobileBreakpoint: 768 },
} as const
```

- [ ] **Step 2: Add i18n initialization and copy**

Initialize `i18next` with one `zh-CN` resource and add keys for the app name, navigation, dashboard headings, metrics, quick actions, issues, inventory and shared empty/error actions. Do not introduce English fallback text into JSX.

- [ ] **Step 3: Wire theme and i18n into the app entry**

Import `@/i18n`, pass `appTheme` to `ConfigProvider`, retain the existing `SoybeanCommonMain` boot flow, and keep `zhCN` as the AntD locale.

- [ ] **Step 4: Replace global styles with token-backed base styles**

Expose stable CSS custom properties from the same approved palette, set the page background and typography, and add visible `:focus-visible` treatment. Do not use `gap`, `backdrop-filter`, `position: sticky`, `clamp()` or container queries.

- [ ] **Step 5: Verify theme compilation**

Run: `cd front && npm run type-check && npm run lint`

Expected: both commands exit 0 with no warnings.

- [ ] **Step 6: Commit theme infrastructure**

```bash
git add front/src/theme front/src/i18n front/src/main.tsx front/src/index.css
git commit -m "feat(front): add asset system design tokens"
```

## Task 3: Build configuration-driven responsive AppShell

**Files:**

- Create: `front/src/config/navigation.ts`
- Create: `front/src/layouts/AppShell/index.tsx`
- Create: `front/src/layouts/AppShell/AppShell.css`
- Modify: `front/src/router/index.tsx`
- Modify: `front/src/types/index.ts`
- Delete: `front/src/components/Layout.tsx`

- [ ] **Step 1: Add concrete navigation configuration**

Define desktop entries for home, asset ledger, business flows, inventory, approvals, import/export, master data, permissions and logs. Mark unfinished routes disabled so they remain useful layout references without navigating to 404. Mark home, assets, inventory and profile as the four mobile destinations.

Extend `User` with `permissions?: string[]` so the shell can filter entries when the authentication API provides button/menu permissions. Entries without a permission requirement remain visible during the local prototype stage.

- [ ] **Step 2: Implement the desktop shell**

Build a semantic rail with the asset-system cube mark, icon buttons, translated tooltips, selected state and bottom user/settings controls. Keep the route outlet in a centered content container and use Lucide icons only.

- [ ] **Step 3: Implement mobile navigation**

Below 768px, hide the desktop rail, show the four-item bottom navigation, and provide an AntD drawer for the remaining permitted destinations. Disabled routes must expose `aria-disabled="true"` and must not navigate.

- [ ] **Step 4: Connect the router**

Lazy-load `Home`, wrap it with the existing `ProtectedRoute`, use `AppShell` as the protected route layout, and preserve login and 404 behavior.

- [ ] **Step 5: Verify model and shell compilation**

Run: `cd front && npm test && npm run type-check && npm run lint`

Expected: all tests pass; TypeScript and ESLint exit 0.

- [ ] **Step 6: Commit the shell**

```bash
git add front/src/config/navigation.ts front/src/layouts/AppShell front/src/router/index.tsx front/src/components/Layout.tsx
git commit -m "feat(front): build responsive asset app shell"
```

## Task 4: Build reusable dashboard primitives

**Files:**

- Create: `front/src/components/ui/PageHeader.tsx`
- Create: `front/src/components/ui/MetricCard.tsx`
- Create: `front/src/components/ui/SectionPanel.tsx`
- Create: `front/src/components/ui/StatePanel.tsx`
- Create: `front/src/components/ui/ui.css`

- [ ] **Step 1: Implement focused UI primitives**

`PageHeader` accepts title, description and optional actions. `MetricCard` accepts an icon, label, value, optional unit, semantic tone and optional change text. `SectionPanel` accepts a title, optional extra action and children. `StatePanel` accepts empty/error mode, message and optional retry callback.

- [ ] **Step 2: Apply the shared visual system**

Use white surfaces, light borders, the centralized radius and restrained shadows. Use adjacent-sibling margins instead of CSS `gap`. Every interactive element must have hover, focus-visible and disabled states.

- [ ] **Step 3: Verify primitive compilation**

Run: `cd front && npm run type-check && npm run lint`

Expected: both commands exit 0 with no warnings.

- [ ] **Step 4: Commit the primitives**

```bash
git add front/src/components/ui
git commit -m "feat(front): add reusable dashboard primitives"
```

## Task 5: Compose the responsive asset dashboard

**Files:**

- Create: `front/src/features/dashboard/dashboardData.ts`
- Create: `front/src/features/dashboard/Dashboard.tsx`
- Create: `front/src/features/dashboard/Dashboard.css`
- Modify: `front/src/pages/Home.tsx`

- [ ] **Step 1: Add isolated typed demo data**

Create one `DashboardOverview` value containing the prototype-aligned totals, four issue counts, one active inventory task, category distribution and six months of intake/scrap values. The file must contain data only and must be replaceable by a future React Query result.

Expose it through a small React Query query function so the page exercises loading and query-state composition now; replacing that function with `dashboardApi.getOverview` must not change presentation components.

- [ ] **Step 2: Build the first viewport**

Compose `PageHeader`, four `MetricCard` instances, four permission-ready quick actions, an actionable issues list and the active inventory progress panel. Preserve the prototypes' information hierarchy while using the approved light palette.

Render an AntD skeleton while the query is loading, `StatePanel` in error mode with a working retry action after query failure, and `StatePanel` in empty mode when the returned overview contains no assets. Keep restricted values absent from the component tree instead of masking them with CSS.

- [ ] **Step 3: Build lower statistics**

Render category and status distribution as readable horizontal bars and monthly intake/scrap as a lightweight CSS/SVG trend. Include visible labels and values so meaning never depends on color alone.

- [ ] **Step 4: Add responsive behavior**

Use four metrics per row on wide screens, two on medium screens and one on narrow screens. Stack quick actions, issues, inventory and statistics in reading order on mobile. Avoid horizontal overflow and ensure a 44px minimum touch target.

- [ ] **Step 5: Keep the route page thin**

Replace the scaffold `Home` contents with a default export of `Dashboard`; remove the `helloApi` query from the page without modifying the shared HTTP client.

- [ ] **Step 6: Run all static checks**

Run: `cd front && npm test && npm run type-check && npm run lint && npm run build`

Expected: tests pass, ESLint has zero warnings, TypeScript has zero errors, and Vite completes a production build.

- [ ] **Step 7: Commit the dashboard**

```bash
git add front/src/features/dashboard front/src/pages/Home.tsx
git commit -m "feat(front): build asset dashboard"
```

## Task 6: Browser and visual verification

**Files:**

- Modify only files from Tasks 2–5 when a verified defect requires a fix.

- [ ] **Step 1: Start the frontend**

Run: `npm run dev:front -- --host 127.0.0.1`

Expected: Vite reports a local URL and the page loads without console errors.

- [ ] **Step 2: Verify the authenticated route**

Use the existing development login flow or persisted local authentication to open `/home`. Verify desktop navigation selection, tooltips, disabled destinations, user menu and dashboard content.

- [ ] **Step 3: Compare desktop layout to references**

Capture the page near the supplied prototype viewport. Compare these five points: narrow rail geometry, content alignment, metric hierarchy, quick-action/todo balance and lower statistics density. The palette must remain the approved light theme.

- [ ] **Step 4: Verify responsive views**

Check a small laptop width and a mobile width. Confirm the desktop rail disappears, bottom navigation and more drawer work, cards reflow, touch targets remain usable and no horizontal overflow occurs.

- [ ] **Step 5: Inspect screenshots directly**

Use `view_image` on the supplied prototype and the latest implementation screenshot in the same QA pass. Record and fix any remaining layout, typography, spacing, icon or density mismatch that conflicts with the approved design.

- [ ] **Step 6: Run final verification**

Run: `cd front && npm test && npm run type-check && npm run lint && npm run build`

Expected: every command exits 0; no warnings or build errors remain.

- [ ] **Step 7: Commit verified fixes**

```bash
git add front/src
git commit -m "fix(front): polish responsive dashboard"
```
