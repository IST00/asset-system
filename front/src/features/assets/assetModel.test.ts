import assert from 'node:assert/strict'
import test from 'node:test'
import {
  canViewAssets,
  canViewAmount,
  getOrderedAssetStatuses,
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
  assert.deepEqual(parseAssetCodes(''), [])
  assert.deepEqual(parseAssetCodes('PC-004，PC-005，PC-004'), ['PC-004', 'PC-005'])
  assert.deepEqual(parseAssetCodes('__proto__, constructor, __proto__'), [
    '__proto__',
    'constructor',
  ])
})

test('returns stable metadata for every supported status', () => {
  assert.equal(getAssetStatusMeta('IDLE').labelKey, 'assets.status.idle')
  assert.equal(getAssetStatusMeta('PENDING_RECEIPT').labelKey, 'assets.status.pendingReceipt')
  assert.equal(getAssetStatusMeta('IN_USE').labelKey, 'assets.status.inUse')
  assert.equal(getAssetStatusMeta('REPAIRING').labelKey, 'assets.status.repairing')
  assert.equal(getAssetStatusMeta('SCRAPPED').labelKey, 'assets.status.scrapped')
  assert.equal(getAssetStatusMeta('SCRAPPED').tone, 'slate')
  assert.equal(Object.isFrozen(getAssetStatusMeta('IDLE')), true)
})

test('returns every status in strictly increasing shared metadata order', () => {
  const statuses = getOrderedAssetStatuses()

  assert.deepEqual(statuses, ['IDLE', 'PENDING_RECEIPT', 'IN_USE', 'REPAIRING', 'SCRAPPED'])
  assert.equal(Object.isFrozen(statuses), true)
  for (let index = 1; index < statuses.length; index += 1) {
    const previousStatus = statuses[index - 1]
    const currentStatus = statuses[index]
    assert.ok(previousStatus !== undefined)
    assert.ok(currentStatus !== undefined)
    assert.ok(getAssetStatusMeta(previousStatus).order < getAssetStatusMeta(currentStatus).order)
  }
})

test('shows amount only to an explicitly permitted user', () => {
  assert.equal(canViewAmount(undefined), false)
  assert.equal(canViewAmount([]), false)
  assert.equal(canViewAmount(['asset:amount:view']), true)
})

test('requires an explicit asset view permission', () => {
  assert.equal(canViewAssets(undefined), false)
  assert.equal(canViewAssets([]), false)
  assert.equal(canViewAssets(['stock-in:create']), false)
  assert.equal(canViewAssets(['asset:view']), true)
})

test('normalizes optional form values without changing snake_case fields', () => {
  assert.deepEqual(
    normalizeAssetPayload({
      asset_name: '  MacBook Pro  ',
      company_name: '总部',
      usage_company_name: '上海公司',
      usage_department_name: '研发部',
      holder_user_name: undefined,
      category_name: '电脑设备',
      source_name: '采购',
      unit_name: '台',
      supplier_name: '   ',
      purchase_date: '2026-07-21',
      location_name: '上海/研发部/A区',
      purchase_amount: 0,
      zero_amount_reason: '  赠品  ',
      model: '',
      serial_number: '',
      manager_name: '  周明  ',
      remark: '',
    }),
    {
      asset_name: 'MacBook Pro',
      company_name: '总部',
      usage_company_name: '上海公司',
      usage_department_name: '研发部',
      holder_user_name: undefined,
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
      rfid_tag: undefined,
      change_reason: undefined,
      remark: undefined,
    },
  )
})
