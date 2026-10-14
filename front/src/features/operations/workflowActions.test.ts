import assert from 'node:assert/strict'
import test from 'node:test'
import { canHandleLocalFeishuDecision } from './workflowActions.ts'

test('allows an asset manager to decide a pending local Feishu personal return', () => {
  assert.equal(
    canHandleLocalFeishuDecision(
      {
        operation_type: 'PERSONAL_RETURN',
        approval_status: 'PENDING',
        external_instance_id: 'LOCAL-FEISHU-2',
      },
      true,
    ),
    true,
  )
})

test('hides local Feishu decisions from unauthorized or non-pending records', () => {
  const record = {
    operation_type: 'PERSONAL_RETURN',
    approval_status: 'PENDING',
    external_instance_id: 'LOCAL-FEISHU-2',
  }
  assert.equal(canHandleLocalFeishuDecision(record, false), false)
  assert.equal(
    canHandleLocalFeishuDecision({ ...record, approval_status: 'APPROVED' }, true),
    false,
  )
  assert.equal(
    canHandleLocalFeishuDecision({ ...record, external_instance_id: 'FEISHU-2' }, true),
    false,
  )
})
