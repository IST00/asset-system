import assert from 'node:assert/strict'
import test from 'node:test'
import type { OperationRequest } from '@/api/operations'
import { filterMyAssets, filterWorkflowRecords } from './workbenchViews.ts'

const record = (overrides: Partial<OperationRequest>): OperationRequest => ({
  id: 1,
  request_no: 'REQ-1',
  operation_type: 'PERSONAL_USE',
  applicant_id: 1,
  target_user_id: 2,
  approval_status: 'APPROVED',
  execution_status: 'NOT_STARTED',
  assets: [],
  ...overrides,
})

test('Admin 代办申请只出现在目标员工的发给我和待签收视图', () => {
  const delegated = record({
    applicant_id: 1,
    target_user_id: 2,
    fulfillment_status: 'PENDING_SIGN',
  })
  const records = [delegated]
  const status = () => '待员工签收'

  assert.deepEqual(filterWorkflowRecords(records, 'CREATED_BY_ME', 2, status), [])
  assert.deepEqual(filterWorkflowRecords(records, 'ASSIGNED_TO_ME', 2, status), [delegated])
  assert.deepEqual(filterWorkflowRecords(records, 'PENDING_MY_SIGN', 2, status), [delegated])
})

test('收到的成功交接按目标员工展示', () => {
  const transfer = record({
    operation_type: 'TRANSFER',
    target_user_id: 2,
    execution_status: 'SUCCESS',
  })
  assert.deepEqual(
    filterWorkflowRecords([transfer], 'RECEIVED_HANDOVER', 2, () => '已完成'),
    [transfer],
  )
})

test('当前资产视图区分在用和借用', () => {
  const assets = [
    {
      id: 1,
      asset_code: 'A-1',
      asset_name: '电脑',
      status: 'IN_USE' as const,
      usage_mode: 'USE' as const,
      expected_return_at: null,
    },
    {
      id: 2,
      asset_code: 'A-2',
      asset_name: '借用电脑',
      status: 'IN_USE' as const,
      usage_mode: 'BORROW' as const,
      expected_return_at: '2026-09-10T00:00:00Z',
    },
  ]
  assert.deepEqual(filterMyAssets(assets, 'MY_IN_USE'), [assets[0]])
  assert.deepEqual(filterMyAssets(assets, 'MY_BORROWED'), [assets[1]])
  assert.deepEqual(filterMyAssets(assets, 'PENDING_MY_RETURN'), [assets[1]])
})
