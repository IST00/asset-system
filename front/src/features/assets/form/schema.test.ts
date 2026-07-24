import assert from 'node:assert/strict'
import test from 'node:test'
import { assetFormSchema, getAssetFormMode } from './schema.ts'

const valid = {
  asset_name: 'MacBook Pro',
  company_name: '总部',
  category_name: '电脑设备',
  source_name: '采购',
  unit_name: '台',
  supplier_name: '示例供应商',
  purchase_date: '2026-07-21',
  location_name: '上海/研发部/A区',
  purchase_amount: 12999,
  zero_amount_reason: '',
  model: '',
  serial_number: '',
  manager_name: '周明',
  remark: '',
}

test('accepts complete required form data', () => {
  assert.equal(assetFormSchema.safeParse(valid).success, true)
})

test('requires an asset manager', () => {
  const result = assetFormSchema.safeParse({ ...valid, manager_name: '' })

  assert.equal(result.success, false)
  if (!result.success) {
    assert.equal(
      result.error.issues.find((issue) => issue.path[0] === 'manager_name')?.message,
      'assets.form.errors.managerRequired',
    )
  }
})

test('accepts a missing supplier', () => {
  const withoutSupplier: Partial<typeof valid> = { ...valid }
  delete withoutSupplier.supplier_name

  assert.equal(assetFormSchema.safeParse(withoutSupplier).success, true)
  assert.equal(assetFormSchema.safeParse({ ...valid, supplier_name: '' }).success, true)
})

test('uses translation keys for every missing required field', () => {
  const result = assetFormSchema.safeParse({})

  assert.equal(result.success, false)
  if (!result.success) {
    assert.ok(result.error.issues.every((issue) => issue.message.startsWith('assets.form.errors.')))
    assert.equal(
      result.error.issues.find((issue) => issue.path[0] === 'asset_name')?.message,
      'assets.form.errors.assetNameRequired',
    )
    assert.equal(
      result.error.issues.find((issue) => issue.path[0] === 'purchase_amount')?.message,
      'assets.form.errors.required',
    )
  }
})

test('rejects a negative purchase amount', () => {
  assert.equal(assetFormSchema.safeParse({ ...valid, purchase_amount: -1 }).success, false)
})

test('requires a reason for zero amount', () => {
  const result = assetFormSchema.safeParse({ ...valid, purchase_amount: 0 })

  assert.equal(result.success, false)
  if (!result.success) {
    assert.equal(result.error.issues[0]?.message, 'assets.form.errors.zeroAmountReason')
  }
})

test('derives create and edit mode from route params', () => {
  assert.deepEqual(getAssetFormMode(undefined), { mode: 'create' })
  assert.deepEqual(getAssetFormMode('12'), { mode: 'edit', assetId: 12 })
  assert.equal(getAssetFormMode('invalid'), null)
})
