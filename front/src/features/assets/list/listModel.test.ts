import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { getAssetStatusMeta, getOrderedAssetStatuses } from '../assetModel.ts'
import {
  canCreateAsset,
  buildAssetListQuery,
  getAssetStatusOptions,
  getAvailableColumns,
  getDefaultColumns,
  getNextQueryRevision,
} from './listModel.ts'

test('builds an explicit query and resets a new search to page one', () => {
  assert.deepEqual(
    buildAssetListQuery({ keyword: ' MacBook ', assetCodesText: 'PC-001, PC-002\nPC-001' }, 50),
    { keyword: 'MacBook', asset_codes: ['PC-001', 'PC-002'], page: 1, size: 50 },
  )
})

test('builds a current-holder-only query when requested', () => {
  assert.deepEqual(buildAssetListQuery({ keyword: ' MacBook ', only_my_assets: true }, 50), {
    keyword: 'MacBook',
    only_my_assets: true,
    page: 1,
    size: 50,
  })
})

test('hides amount configuration without permission', () => {
  assert.equal(getAvailableColumns([]).includes('purchase_amount'), false)
  assert.equal(getAvailableColumns(['asset:amount:view']).includes('purchase_amount'), true)
})

test('shows create only for a product or stock-in create permission', () => {
  assert.equal(canCreateAsset(undefined), false)
  assert.equal(canCreateAsset([]), false)
  assert.equal(canCreateAsset(['asset:view']), false)
  assert.equal(canCreateAsset(['asset:create']), true)
  assert.equal(canCreateAsset(['stock-in:create']), true)
})

test('advances the query revision for every explicit search', () => {
  assert.equal(getNextQueryRevision(0), 1)
  assert.equal(getNextQueryRevision(7), 8)
})

test('keeps the documented desktop defaults and compact mobile fields', () => {
  assert.deepEqual(getDefaultColumns('mobile'), [
    'asset_code',
    'asset_name',
    'status',
    'category_name',
  ])
  assert.equal(getDefaultColumns('desktop').includes('purchase_amount'), false)
})

test('derives every status option from the shared ordering and metadata contracts', () => {
  const options = getAssetStatusOptions()
  const sharedStatuses = getOrderedAssetStatuses()
  const source = readFileSync(new URL('./listModel.ts', import.meta.url), 'utf8')

  assert.deepEqual(
    options,
    sharedStatuses.map((status) => ({ value: status, meta: getAssetStatusMeta(status) })),
  )
  assert.equal(source.includes('getOrderedAssetStatuses()'), true)
  assert.equal(source.includes('assetStatusOrder'), false)
})
