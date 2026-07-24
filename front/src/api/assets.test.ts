import assert from 'node:assert/strict'
import test from 'node:test'
import { createAsset, getAsset, listAssets, updateAsset } from './assets.ts'
import { demoAssets } from '../features/assets/assetData.ts'
import type { AssetListQuery, AssetPayload } from '../features/assets/types.ts'

const buildPayload = (assetName: string): AssetPayload => ({
  asset_name: assetName,
  company_name: '星河科技（上海）有限公司',
  category_name: '电脑设备',
  source_name: '采购',
  unit_name: '台',
  supplier_name: '上海云创数码有限公司',
  purchase_date: '2026-07-21',
  location_name: '上海总部/行政库房/T-01',
  purchase_amount: 6999,
  manager_name: '周明',
})

test('filters exact pasted asset codes and paginates safely', async () => {
  const result = await listAssets({
    asset_codes: ['PC-2026-001', 'MO-2026-001'],
    page: 1,
    size: 20,
  })

  assert.deepEqual(
    result.records.map((item) => item.asset_code),
    ['PC-2026-001', 'MO-2026-001'],
  )
  assert.equal(result.total, 2)
})

test('matches every declared keyword field with exact results', async () => {
  const cases = [
    { keyword: 'PC-2026-001', expectedCodes: ['PC-2026-001'] },
    { keyword: 'UltraSharp', expectedCodes: ['DS-2026-001'] },
    { keyword: 'F2LPH2025018', expectedCodes: ['PH-2025-018'] },
    { keyword: '林晓宇', expectedCodes: ['PC-2026-001'] },
    { keyword: 'SH-2026-0712-002', expectedCodes: ['MO-2026-001'] },
  ]

  for (const item of cases) {
    const result = await listAssets({ keyword: item.keyword, page: 1, size: 20 })
    assert.equal(result.total, item.expectedCodes.length)
    assert.deepEqual(
      result.records.map((asset) => asset.asset_code),
      item.expectedCodes,
    )
  }
})

test('applies every declared exact filter and inclusive purchase date boundary', async () => {
  const cases: Array<{
    query: Partial<AssetListQuery>
    expectedCodes: string[]
  }> = [
    {
      query: { company_name: '星河科技（北京）有限公司' },
      expectedCodes: ['DS-2026-001', 'NB-2020-032', 'FU-2025-026'],
    },
    {
      query: { category_name: '移动设备' },
      expectedCodes: ['PH-2025-018', 'TB-2026-004'],
    },
    {
      query: { status: 'REPAIRING' },
      expectedCodes: ['PH-2025-018', 'PR-2021-006', 'CA-2023-007', 'PJ-2019-002'],
    },
    {
      query: { department_name: '产品中心' },
      expectedCodes: ['DS-2026-001'],
    },
    {
      query: { location_name: '上海总部/行政库房/B-03' },
      expectedCodes: ['MO-2026-001'],
    },
    {
      query: { information_complete: false },
      expectedCodes: ['PR-2021-006', 'CA-2023-007', 'FU-2025-026', 'PJ-2019-002'],
    },
    {
      query: { user_name: '林晓宇' },
      expectedCodes: ['PC-2026-001'],
    },
    {
      query: { manager_name: '赵海' },
      expectedCodes: ['PH-2025-018', 'TB-2026-004', 'PJ-2019-002'],
    },
    {
      query: { supplier_name: '上海云创数码有限公司' },
      expectedCodes: ['PC-2026-001', 'MO-2026-001', 'PC-2022-015'],
    },
    {
      query: { source_name: '赠予' },
      expectedCodes: ['TB-2026-004'],
    },
    {
      query: { purchase_date_from: '2026-07-12', purchase_date_to: '2026-07-12' },
      expectedCodes: ['PC-2026-001', 'MO-2026-001'],
    },
  ]

  for (const item of cases) {
    const result = await listAssets({ ...item.query, page: 1, size: 20 })
    assert.equal(result.total, item.expectedCodes.length)
    assert.deepEqual(
      result.records.map((asset) => asset.asset_code),
      item.expectedCodes,
    )
  }
})

test('normalizes invalid pages and runtime-invalid page sizes', async () => {
  for (const page of [-1, 0, 2.5, 999, Number.NaN]) {
    const result = await listAssets({ page, size: 20 })
    assert.equal(result.page, 1)
  }

  const invalidSizeQuery = { page: 1, size: 10 } as unknown as AssetListQuery
  const defaultSized = await listAssets(invalidSizeQuery)
  assert.equal(defaultSized.size, 50)
})

test('keeps the exported demo fixture deeply frozen', () => {
  assert.equal(Object.isFrozen(demoAssets), true)
  assert.ok(demoAssets.every((asset) => Object.isFrozen(asset)))
})

test('persists a created asset without changing the demo fixture', async () => {
  const fixtureBefore = JSON.stringify(demoAssets)
  const created = await createAsset(buildPayload('持久化测试资产'))
  const fetched = await getAsset(created.id)

  assert.deepEqual(fetched, created)
  assert.equal(JSON.stringify(demoAssets), fixtureBefore)
})

test('persists an immutable update for get and list without changing the demo fixture', async () => {
  const fixtureBefore = JSON.stringify(demoAssets)
  const original = await getAsset(1)
  const updated = await updateAsset(1, buildPayload('更新后的唯一资产名称'))
  const fetched = await getAsset(1)
  const listed = await listAssets({ keyword: '更新后的唯一资产名称', page: 1, size: 20 })

  assert.notEqual(updated, original)
  assert.deepEqual(fetched, updated)
  assert.equal(listed.total, 1)
  assert.equal(listed.records[0]?.id, 1)
  assert.equal(JSON.stringify(demoAssets), fixtureBefore)
})

test('assigns monotonic unique IDs and current-year codes to consecutive creates', async () => {
  const first = await createAsset(buildPayload('连续创建资产一'))
  const second = await createAsset(buildPayload('连续创建资产二'))
  const currentYear = String(new Date().getFullYear())

  assert.ok(second.id > first.id)
  assert.notEqual(second.id, first.id)
  assert.notEqual(second.asset_code, first.asset_code)
  assert.ok(first.asset_code.indexOf(`PC-${currentYear}-`) === 0)
  assert.ok(second.asset_code.indexOf(`PC-${currentYear}-`) === 0)
})

test('rejects a missing asset without exposing another record', async () => {
  await assert.rejects(() => getAsset(999999), /ASSET_NOT_FOUND/)
})
