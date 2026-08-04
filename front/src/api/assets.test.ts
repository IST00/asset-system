import assert from 'node:assert/strict'
import test from 'node:test'
import { mapBackendAsset, type BackendAsset } from './assetMapper.ts'

const backendAsset: BackendAsset = {
  id: 7,
  asset_code: 'ZC-0007',
  asset_name: 'MacBook Pro',
  status: 'IDLE',
  version: 2,
  organization_id: 1,
  category_id: 2,
  manager_id: 3,
  company_name: '读书科技',
  category_name: '电脑设备',
  unit_name: '台',
  source_name: '采购',
  location_name: '北京总部',
  purchase_date: '2026-07-20',
  original_amount: '12999.50',
  data_completeness: 'COMPLETE',
  specification_model: 'M4 Pro',
  receipt_no: 'FP-20260720-01',
  created_at: '2026-07-20T10:00:00+08:00',
  updated_at: '2026-07-21T10:00:00+08:00',
}

test('maps backend asset fields to the glass frontend model', () => {
  const asset = mapBackendAsset(backendAsset)

  assert.equal(asset.id, 7)
  assert.equal(asset.purchase_amount, 12999.5)
  assert.equal(asset.information_complete, true)
  assert.equal(asset.model, 'M4 Pro')
  assert.equal(asset.receipt_number, 'FP-20260720-01')
})

test('uses explicit frontend fallbacks for missing reference names', () => {
  const asset = mapBackendAsset({
    ...backendAsset,
    company_name: null,
    category_name: null,
    unit_name: null,
    source_name: null,
    location_name: null,
    data_completeness: 'INCOMPLETE',
  })

  assert.equal(asset.company_name, '未配置所属公司')
  assert.equal(asset.category_name, '未配置资产分类')
  assert.equal(asset.information_complete, false)
})
