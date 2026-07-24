# Asset Ledger Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build responsive asset list, asset detail, and shared create/edit pages on top of one frozen typed asset contract.

**Architecture:** The root task first owns and freezes shared asset types, status/query helpers, typed demo data, API adapters, test discovery, and all i18n keys. Three workers then implement list, detail, and form feature directories without touching shared files; the root task finally integrates routes and navigation and runs full browser QA.

**Tech Stack:** React 18, TypeScript, Vite 5, Ant Design 5, Lucide React, React Router 6, React Query 5, React Hook Form 7, Zod 3, i18next, Node.js 22 test runner.

---

## Ownership map

### Root-only shared files

```text
front/package.json
front/src/features/assets/types.ts
front/src/features/assets/assetModel.ts
front/src/features/assets/assetModel.test.ts
front/src/features/assets/assetData.ts
front/src/api/assets.ts
front/src/api/assets.test.ts
front/src/i18n/zhCN.ts
front/src/router/index.tsx
front/src/config/navigation.ts
```

### Parallel worker files

```text
List worker:
  front/src/features/assets/list/**
  front/src/pages/Assets.tsx

Detail worker:
  front/src/features/assets/detail/**
  front/src/pages/AssetDetail.tsx

Form worker:
  front/src/features/assets/form/**
  front/src/pages/AssetForm.tsx
```

Workers must not modify root-only files, package files, theme, AppShell, HTTP client, dashboard, or another worker's directory.

## Task 1: Freeze shared asset contracts and demo API

**Files:**

- Modify: `front/package.json`
- Create: `front/src/features/assets/types.ts`
- Create: `front/src/features/assets/assetModel.test.ts`
- Create: `front/src/features/assets/assetModel.ts`
- Create: `front/src/features/assets/assetData.ts`
- Create: `front/src/api/assets.ts`
- Create: `front/src/api/assets.test.ts`
- Modify: `front/src/i18n/zhCN.ts`

- [ ] **Step 1: Make test discovery concurrency-safe**

Replace the explicit test file list with Node 22's quoted recursive glob:

```json
"test": "node --experimental-strip-types --test \"src/**/*.test.ts\""
```

This allows workers to add tests without editing `package.json`.

- [ ] **Step 2: Write failing shared-model tests**

Create tests with these exact behaviors:

```ts
import assert from 'node:assert/strict'
import test from 'node:test'
import {
  canViewAmount,
  getAssetStatusMeta,
  normalizeAssetPayload,
  parseAssetCodes,
} from './assetModel.ts'

test('parses pasted asset codes, removes blanks, and preserves first occurrence order', () => {
  assert.deepEqual(parseAssetCodes('PC-001, PC-002\nPC-001  PC-003'), [
    'PC-001',
    'PC-002',
    'PC-003',
  ])
})

test('returns stable metadata for every supported status', () => {
  assert.equal(getAssetStatusMeta('IDLE').labelKey, 'assets.status.idle')
  assert.equal(getAssetStatusMeta('SCRAPPED').tone, 'slate')
})

test('shows amount only to an explicitly permitted user', () => {
  assert.equal(canViewAmount(undefined), false)
  assert.equal(canViewAmount([]), false)
  assert.equal(canViewAmount(['asset:amount:view']), true)
})

test('normalizes optional form values without changing snake_case fields', () => {
  assert.deepEqual(
    normalizeAssetPayload({
      asset_name: '  MacBook Pro  ',
      company_name: '总部',
      category_name: '电脑设备',
      source_name: '采购',
      unit_name: '台',
      supplier_name: '',
      purchase_date: '2026-07-21',
      location_name: '上海/研发部/A区',
      purchase_amount: 0,
      zero_amount_reason: '  赠品  ',
      model: '',
      serial_number: '',
      manager_name: '周明',
      remark: '',
    }),
    {
      asset_name: 'MacBook Pro',
      company_name: '总部',
      category_name: '电脑设备',
      source_name: '采购',
      unit_name: '台',
      supplier_name: undefined,
      purchase_date: '2026-07-21',
      location_name: '上海/研发部/A区',
      purchase_amount: 0,
      zero_amount_reason: '赠品',
      model: undefined,
      serial_number: undefined,
      manager_name: '周明',
      remark: undefined,
    },
  )
})
```

- [ ] **Step 3: Run tests and verify RED**

Run: `cd front && npm test`

Expected: the new test fails because `assetModel.ts` does not exist; existing dashboard and navigation tests remain green.

- [ ] **Step 4: Define the shared types**

Create these exported contracts:

```ts
export type AssetStatus = 'IDLE' | 'IN_USE' | 'REPAIRING' | 'SCRAPPED'
export type AssetTone = 'brand' | 'success' | 'warning' | 'danger' | 'slate'

export interface AssetSummary {
  id: number
  asset_code: string
  asset_name: string
  category_name: string
  status: AssetStatus
  model?: string
  serial_number?: string
  receipt_number?: string
  user_name?: string
  department_name?: string
  location_name: string
  manager_name?: string
  company_name: string
  supplier_name?: string
  source_name: string
  unit_name: string
  purchase_date: string
  purchase_amount: number
  information_complete: boolean
}

export interface AssetDetail extends AssetSummary {
  zero_amount_reason?: string
  remark?: string
  created_at: string
  updated_at: string
}

export interface AssetListQuery {
  keyword?: string
  asset_codes?: string[]
  company_name?: string
  category_name?: string
  status?: AssetStatus
  department_name?: string
  location_name?: string
  information_complete?: boolean
  user_name?: string
  manager_name?: string
  supplier_name?: string
  source_name?: string
  purchase_date_from?: string
  purchase_date_to?: string
  page: number
  size: 20 | 50 | 100
}

export interface AssetFormValues {
  asset_name: string
  company_name: string
  category_name: string
  source_name: string
  unit_name: string
  supplier_name?: string
  purchase_date: string
  location_name: string
  purchase_amount: number
  zero_amount_reason?: string
  model?: string
  serial_number?: string
  manager_name: string
  remark?: string
}

export type AssetPayload = AssetFormValues
```

- [ ] **Step 5: Implement minimal shared helpers**

Implement `parseAssetCodes`, `getAssetStatusMeta`, `canViewAmount`, and `normalizeAssetPayload`. `parseAssetCodes` splits on whitespace and Chinese/English commas, trims values, drops empty values, and keeps first-occurrence order.

- [ ] **Step 6: Verify GREEN**

Run: `cd front && npm test && npm run type-check && npm run lint`

Expected: all tests pass, TypeScript has zero errors, ESLint has zero warnings.

- [ ] **Step 7: Write failing demo API tests**

```ts
import assert from 'node:assert/strict'
import test from 'node:test'
import { getAsset, listAssets } from './assets.ts'

test('filters exact pasted asset codes and paginates safely', async () => {
  const result = await listAssets({ asset_codes: ['PC-2026-001', 'MO-2026-001'], page: 1, size: 20 })
  assert.deepEqual(result.records.map((item) => item.asset_code), ['PC-2026-001', 'MO-2026-001'])
  assert.equal(result.total, 2)
})

test('matches keyword fields and clamps a page past the result set', async () => {
  const result = await listAssets({ keyword: 'MacBook', page: 99, size: 20 })
  assert.ok(result.records.every((item) => item.asset_name.includes('MacBook')))
  assert.equal(result.page, 1)
})

test('rejects a missing asset without exposing another record', async () => {
  await assert.rejects(() => getAsset(999999), /ASSET_NOT_FOUND/)
})
```

- [ ] **Step 8: Run API tests and verify RED**

Run: `cd front && npm test`

Expected: FAIL because `assets.ts` and the demo records do not exist.

- [ ] **Step 9: Add typed demo data and Promise API**

Create 12 realistic `AssetDetail` records covering all four statuses, multiple companies/categories/locations, complete and incomplete records, zero and non-zero amounts, and assigned/unassigned users.

Implement these functions in `front/src/api/assets.ts`:

```ts
export function listAssets(query: AssetListQuery): Promise<PageResult<AssetSummary>>
export function getAsset(assetId: number): Promise<AssetDetail>
export function createAsset(payload: AssetPayload): Promise<AssetDetail>
export function updateAsset(assetId: number, payload: AssetPayload): Promise<AssetDetail>
```

`listAssets` applies exact multi-code matching, contains matching for keyword fields, all declared filters, and page bounds. `getAsset` rejects with `Error('ASSET_NOT_FOUND')` when missing. Create/update return new objects and do not mutate exported demo fixtures.

Because `assets.test.ts` runs directly in Node, `assets.ts` must use relative imports with explicit `.ts` extensions for shared types/data rather than the Vite-only `@/` alias.

- [ ] **Step 10: Add all shared translation keys**

Add `assets.*` resources for list filters, columns, statuses, pagination, selection confirmation, detail tabs and fields, form sections/labels/actions, validation error keys, loading/empty/error states, unsaved-change confirmation, and success feedback. Workers consume keys but do not edit resources.

- [ ] **Step 11: Verify the shared contract**

Run: `cd front && npm test && npm run type-check && npm run lint`

Expected: all commands exit 0.

## Task 2: Asset list page (parallel worker A)

**Files:**

- Create: `front/src/features/assets/list/listModel.test.ts`
- Create: `front/src/features/assets/list/listModel.ts`
- Create: `front/src/features/assets/list/AssetList.tsx`
- Create: `front/src/features/assets/list/AssetList.css`
- Create: `front/src/pages/Assets.tsx`

- [ ] **Step 1: Write failing list-model tests**

```ts
import assert from 'node:assert/strict'
import test from 'node:test'
import { buildAssetListQuery, getAvailableColumns, getDefaultColumns } from './listModel.ts'

test('builds an explicit query and resets a new search to page one', () => {
  assert.deepEqual(
    buildAssetListQuery({ keyword: ' MacBook ', assetCodesText: 'PC-001, PC-002' }, 50),
    { keyword: 'MacBook', asset_codes: ['PC-001', 'PC-002'], page: 1, size: 50 },
  )
})

test('hides amount configuration without permission', () => {
  assert.equal(getAvailableColumns([]).includes('purchase_amount'), false)
  assert.equal(getAvailableColumns(['asset:amount:view']).includes('purchase_amount'), true)
})

test('keeps the documented desktop defaults and compact mobile fields', () => {
  assert.deepEqual(getDefaultColumns('mobile'), ['asset_code', 'asset_name', 'status', 'category_name'])
  assert.equal(getDefaultColumns('desktop').includes('purchase_amount'), false)
})
```

- [ ] **Step 2: Run the worker test and verify RED**

Run: `cd front && npm test`

Expected: FAIL because `listModel.ts` does not exist.

- [ ] **Step 3: Implement the list model**

Export `buildAssetListQuery`, `getAvailableColumns`, and `getDefaultColumns`. Reuse `parseAssetCodes` and `canViewAmount` from the frozen shared model.

- [ ] **Step 4: Verify GREEN**

Run: `cd front && npm test`

Expected: the new list tests and all existing tests pass.

- [ ] **Step 5: Build the responsive list page**

Use React Query with `listAssets`. Implement an explicit-search filter bar, multi-code modal/textarea, common filters, more-filter drawer, reset, column settings, desktop AntD Table, mobile cards below 768px, current-page selection, all-filtered-results confirmation UI, loading Skeleton, preserved-filter empty state, local error retry, and pagination sizes 20/50/100 with default 50.

The page must navigate to `/assets/:assetId` and `/assets/new` through React Router. Do not implement routes in this worker.

- [ ] **Step 6: Verify the worker output**

Run: `cd front && npm test && npm run type-check && npm run lint`

Expected: all commands exit 0.

## Task 3: Asset detail page (parallel worker B)

**Files:**

- Create: `front/src/features/assets/detail/detailModel.test.ts`
- Create: `front/src/features/assets/detail/detailModel.ts`
- Create: `front/src/features/assets/detail/AssetDetail.tsx`
- Create: `front/src/features/assets/detail/AssetDetail.css`
- Create: `front/src/pages/AssetDetail.tsx`

- [ ] **Step 1: Write failing detail-model tests**

```ts
import assert from 'node:assert/strict'
import test from 'node:test'
import { assetDetailTabs, getDetailFieldGroups } from './detailModel.ts'

test('keeps the confirmed eight-tab order', () => {
  assert.deepEqual(assetDetailTabs.map((tab) => tab.key), [
    'basic', 'attachments', 'relations', 'history', 'repairs', 'scrap', 'inventory', 'approvals',
  ])
})

test('omits purchase amount without explicit permission', () => {
  const hidden = getDetailFieldGroups(false).reduce<string[]>((fields, group) => fields.concat(group.fields), [])
  const visible = getDetailFieldGroups(true).reduce<string[]>((fields, group) => fields.concat(group.fields), [])
  assert.equal(hidden.includes('purchase_amount'), false)
  assert.equal(visible.includes('purchase_amount'), true)
})
```

- [ ] **Step 2: Run the worker test and verify RED**

Run: `cd front && npm test`

Expected: FAIL because `detailModel.ts` does not exist.

- [ ] **Step 3: Implement the detail model**

Export `assetDetailTabs` and `getDetailFieldGroups(canSeeAmount)`. Use translation keys rather than visible Chinese strings.

- [ ] **Step 4: Verify GREEN**

Run: `cd front && npm test`

Expected: the new detail tests and all existing tests pass.

- [ ] **Step 5: Build the responsive detail page**

Read `assetId` from route params, reject invalid numeric IDs locally, fetch through `getAsset`, and render title/code/status/company plus edit/back actions. Render all eight tabs; basic information is complete, while other tabs use structured empty states or local demo records. Hide amount fields without explicit permission. Desktop uses two/three-column descriptions; mobile uses a single-column flow. Include Skeleton, retry, and the non-leaking not-found message.

- [ ] **Step 6: Verify the worker output**

Run: `cd front && npm test && npm run type-check && npm run lint`

Expected: all commands exit 0.

## Task 4: Asset create/edit form (parallel worker C)

**Files:**

- Create: `front/src/features/assets/form/schema.test.ts`
- Create: `front/src/features/assets/form/schema.ts`
- Create: `front/src/features/assets/form/AssetForm.tsx`
- Create: `front/src/features/assets/form/AssetForm.css`
- Create: `front/src/pages/AssetForm.tsx`

- [ ] **Step 1: Write failing schema tests**

```ts
import assert from 'node:assert/strict'
import test from 'node:test'
import { assetFormSchema, getAssetFormMode } from './schema.ts'

const valid = {
  asset_name: 'MacBook Pro', company_name: '总部', category_name: '电脑设备',
  source_name: '采购', unit_name: '台', supplier_name: '示例供应商',
  purchase_date: '2026-07-21', location_name: '上海/研发部/A区',
  purchase_amount: 12999, zero_amount_reason: '', model: '', serial_number: '',
  manager_name: '周明', remark: '',
}

test('accepts complete page-create data and rejects negative amount', () => {
  assert.equal(assetFormSchema.safeParse(valid).success, true)
  assert.equal(assetFormSchema.safeParse({ ...valid, purchase_amount: -1 }).success, false)
})

test('requires a reason for zero amount', () => {
  const result = assetFormSchema.safeParse({ ...valid, purchase_amount: 0 })
  assert.equal(result.success, false)
  if (!result.success) assert.equal(result.error.issues[0]?.message, 'assets.form.errors.zeroAmountReason')
})

test('derives create and edit mode from route params', () => {
  assert.deepEqual(getAssetFormMode(undefined), { mode: 'create' })
  assert.deepEqual(getAssetFormMode('12'), { mode: 'edit', assetId: 12 })
  assert.equal(getAssetFormMode('invalid'), null)
})
```

- [ ] **Step 2: Run the worker test and verify RED**

Run: `cd front && npm test`

Expected: FAIL because `schema.ts` does not exist.

- [ ] **Step 3: Implement the Zod schema**

Export `assetFormSchema`, inferred form input type, and `getAssetFormMode(assetId)`. Zod messages must be `assets.form.errors.*` translation keys so JSX translates them at render time.

- [ ] **Step 4: Verify GREEN**

Run: `cd front && npm test`

Expected: the new form tests and all existing tests pass.

- [ ] **Step 5: Build the shared create/edit form**

Use React Hook Form with `zodResolver`; AntD controls provide layout only, with no duplicated `rules`. Render the five specified sections. In create mode show a generated-code explanation, not an editable code field. In edit mode fetch the asset and show code/status/user/department/location as read-only business fields. Submit with React Query mutation to create/update, keep values on error, navigate to detail on success, and confirm before abandoning dirty changes.

- [ ] **Step 6: Verify the worker output**

Run: `cd front && npm test && npm run type-check && npm run lint`

Expected: all commands exit 0.

## Task 5: Root integration and final verification

**Files:**

- Modify: `front/src/router/index.tsx`
- Modify: `front/src/config/navigation.ts`
- Modify only worker/shared files when review finds a concrete defect.

- [ ] **Step 1: Review file ownership**

Run: `git status --short && git diff --name-only`

Expected: each worker changed only its assigned directories/pages; shared files changed only by the root task.

- [ ] **Step 2: Register lazy routes**

Lazy-load `Assets`, `AssetDetail`, and `AssetForm`, then register:

```tsx
<Route path="assets" element={<Assets />} />
<Route path="assets/new" element={<AssetForm />} />
<Route path="assets/:assetId" element={<AssetDetail />} />
<Route path="assets/:assetId/edit" element={<AssetForm />} />
```

- [ ] **Step 3: Enable asset navigation**

Remove `disabled: true` only from the `assets` navigation entry. Keep all unrelated unfinished modules disabled.

- [ ] **Step 4: Run complete static verification**

Run: `cd front && npm test && npm run type-check && npm run lint && npm run build`

Expected: all tests pass, TypeScript has zero errors, ESLint has zero warnings, and Vite exits 0.

- [ ] **Step 5: Run browser QA**

Verify desktop, small-laptop, and mobile widths for this flow:

```text
/assets -> filter/search -> paginate -> open detail -> switch tabs -> edit -> validation -> save -> detail
```

Also verify `/assets/new`, multi-code parsing, amount permission hiding, empty/error/loading states, no framework overlay, and no relevant console warning/error.

- [ ] **Step 6: Compare visual system**

Check alignment with the accepted dashboard shell: narrow rail, light canvas, white bordered surfaces, blue primary actions, shared typography/radii, Lucide outline icons, 44px touch targets, and mobile cards instead of compressed tables.

- [ ] **Step 7: Run final clean check**

Run: `git diff --check && git status --short --branch`

Expected: no whitespace errors and only intentional `front/` changes remain.
