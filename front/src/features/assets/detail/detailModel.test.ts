import assert from 'node:assert/strict'
import test from 'node:test'
import { assetDetailTabs, getDetailFieldGroups } from './detailModel.ts'

test('asset detail tabs keep the required order', () => {
  assert.deepEqual(
    assetDetailTabs.map((tab) => tab.key),
    ['basic', 'attachments', 'relations', 'history', 'repairs', 'scrap', 'inventory', 'approvals'],
  )
})

test('detail field groups keep the stable order', () => {
  assert.deepEqual(
    getDetailFieldGroups(false).map((group) => group.key),
    ['basic', 'ownership', 'purchase', 'management'],
  )
})

test('detail fields hide financial fields without explicit permission', () => {
  const fields = getDetailFieldGroups(false).reduce<string[]>(
    (result, group) => result.concat(group.fields),
    [],
  )

  assert.equal(fields.includes('purchase_amount'), false)
  assert.equal(fields.includes('zero_amount_reason'), false)
})

test('detail fields include financial fields with explicit permission', () => {
  const fields = getDetailFieldGroups(true).reduce<string[]>(
    (result, group) => result.concat(group.fields),
    [],
  )

  assert.equal(fields.includes('purchase_amount'), true)
  assert.equal(fields.includes('zero_amount_reason'), true)
})
