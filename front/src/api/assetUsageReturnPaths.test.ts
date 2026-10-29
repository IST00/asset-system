import assert from 'node:assert/strict'
import test from 'node:test'
import { localFeishuActionPath } from './assetUsageReturnPaths.ts'

test('uses the return approval endpoint for return operations', () => {
  assert.equal(
    localFeishuActionPath(2, 'PERSONAL_RETURN'),
    '/asset-return-requests/2/mock-feishu-action',
  )
  assert.equal(
    localFeishuActionPath(3, 'PERSONAL_USE'),
    '/asset-usage-requests/3/mock-feishu-action',
  )
})
