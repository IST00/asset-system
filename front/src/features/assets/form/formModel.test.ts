import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildAssetFormPayload,
  canShowAssetAmount,
  getAssetDetailQueryKey,
  getAssetListQueryKey,
  shouldRetryAssetFormQuery,
} from './formModel.ts'

const validValues = {
  asset_name: 'MacBook Pro',
  company_name: '总部',
  usage_company_name: '上海公司',
  category_name: '电脑设备',
  source_name: '采购',
  unit_name: '台',
  supplier_name: '示例供应商',
  purchase_date: '2026-07-21',
  location_name: '上海/研发部/A区',
  purchase_amount: 12999,
  zero_amount_reason: '  历史原因  ',
  model: '',
  serial_number: '',
  manager_name: '周明',
  remark: '',
}

test('keeps a trimmed zero-amount reason only when the amount is zero', () => {
  assert.equal(buildAssetFormPayload(validValues).zero_amount_reason, undefined)
  assert.equal(
    buildAssetFormPayload({ ...validValues, purchase_amount: 0 }).zero_amount_reason,
    '历史原因',
  )
})

test('shows amount for create and only permitted edit forms', () => {
  assert.equal(canShowAssetAmount('create', undefined), true)
  assert.equal(canShowAssetAmount('edit', undefined), false)
  assert.equal(canShowAssetAmount('edit', []), false)
  assert.equal(canShowAssetAmount('edit', ['asset:amount:view']), true)
})

test('protects the original financial snapshot from tampered form values', () => {
  const payload = buildAssetFormPayload(
    { ...validValues, purchase_amount: 0, zero_amount_reason: '篡改原因' },
    { purchase_amount: 8642, zero_amount_reason: '原始原因' },
  )

  assert.equal(payload.purchase_amount, 8642)
  assert.equal(payload.zero_amount_reason, '原始原因')
})

test('does not retry not-found and retries other failures at most once', () => {
  assert.equal(shouldRetryAssetFormQuery(0, new Error('ASSET_NOT_FOUND')), false)
  assert.equal(shouldRetryAssetFormQuery(0, new Error('NETWORK_ERROR')), true)
  assert.equal(shouldRetryAssetFormQuery(1, new Error('NETWORK_ERROR')), false)
})

test('keeps detail and list query key shapes stable', () => {
  assert.deepEqual(getAssetDetailQueryKey(12), ['assets', 'detail', 12])
  assert.deepEqual(getAssetListQueryKey(), ['assets', 'list'])
})
