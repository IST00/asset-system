import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  assetScanActionOptions,
  selectScanAction,
  type AssetScanIntent,
} from './scanIntentModel.ts'

const idleIntent: AssetScanIntent = {
  id: 1,
  asset_code: 'A-001',
  asset_name: 'MacBook Air',
  status: 'IDLE',
  usage_type: null,
  holder_user_id: null,
  public_object_id: null,
  public_object_name: '',
  category_id: 1,
  category_name: '电脑',
  organization_id: 1,
  organization_name: '总公司',
  location_id: 2,
  location_name: '仓库',
  scenarios: ['PERSONAL_USE', 'PERSONAL_BORROW'],
  inventory_task: null,
}

describe('scan intent model', () => {
  it('combines workflow scenarios with the inventory entry', () => {
    const intent: AssetScanIntent = {
      ...idleIntent,
      scenarios: ['PERSONAL_RETURN'],
      inventory_task: {
        task_id: 9,
        task_no: 'INV-001',
        task_name: '季度盘点',
        item_status: 'PENDING',
        pending: true,
      },
    }
    assert.deepEqual(
      assetScanActionOptions(intent).map((action) => action.value),
      ['PERSONAL_RETURN', 'INVENTORY'],
    )
  })

  it('selects the first available action unless the preference is valid', () => {
    assert.equal(selectScanAction(idleIntent), 'PERSONAL_USE')
    assert.equal(selectScanAction(idleIntent, 'PERSONAL_BORROW'), 'PERSONAL_BORROW')
    assert.equal(selectScanAction(idleIntent, 'PUBLIC_RETURN'), 'PERSONAL_USE')
  })

  it('selects an available action for the preferred purpose', () => {
    assert.equal(selectScanAction(idleIntent, undefined, 'BORROW'), 'PERSONAL_BORROW')
    assert.equal(selectScanAction(idleIntent, undefined, 'RETURN'), 'PERSONAL_USE')
  })
})
