export type AssetScanScenario =
  | 'PERSONAL_USE'
  | 'PERSONAL_BORROW'
  | 'PUBLIC_USE'
  | 'PUBLIC_BORROW'
  | 'PERSONAL_RETURN'
  | 'PUBLIC_RETURN'

export type AssetScanAction = AssetScanScenario | 'INVENTORY'

export type AssetScanPurpose = 'USE' | 'BORROW' | 'RETURN' | 'INVENTORY'

export interface AssetScanInventoryTask {
  task_id: number
  task_no: string
  task_name: string
  item_status: string
  pending: boolean
}

export interface AssetScanIntent {
  id: number
  asset_code: string
  asset_name: string
  status: 'IDLE' | 'PENDING_RECEIPT' | 'IN_USE' | 'REPAIRING' | 'SCRAPPED'
  usage_type?: 'PERSONAL' | 'PUBLIC' | null
  holder_user_id?: number | null
  public_object_id?: number | null
  public_object_name?: string | null
  category_id: number
  category_name: string
  organization_id: number
  organization_name: string
  location_id?: number | null
  location_name: string
  scenarios: AssetScanScenario[]
  inventory_task?: AssetScanInventoryTask | null
}

export interface AssetScanActionOption {
  value: AssetScanAction
  label: string
  description: string
}

const actionOptions: Record<AssetScanAction, AssetScanActionOption> = {
  PERSONAL_USE: {
    value: 'PERSONAL_USE',
    label: '个人领用',
    description: '提交审批后由管理员发放并签收。',
  },
  PERSONAL_BORROW: {
    value: 'PERSONAL_BORROW',
    label: '个人借用',
    description: '提交审批并跟踪预计归还时间。',
  },
  PUBLIC_USE: {
    value: 'PUBLIC_USE',
    label: '公共领用',
    description: '将资产投入会议室、直播间等公共对象。',
  },
  PUBLIC_BORROW: {
    value: 'PUBLIC_BORROW',
    label: '公共借用',
    description: '公共对象临时借用并跟踪归还时间。',
  },
  PERSONAL_RETURN: {
    value: 'PERSONAL_RETURN',
    label: '个人退库',
    description: '退回本人当前领用的资产。',
  },
  PUBLIC_RETURN: {
    value: 'PUBLIC_RETURN',
    label: '公共退库',
    description: '管理员验收公共资产并退回闲置。',
  },
  INVENTORY: {
    value: 'INVENTORY',
    label: '去盘点',
    description: '继续完成该资产所在盘点任务的扫码登记。',
  },
}

export const assetScanActionOptions = (intent: AssetScanIntent): AssetScanActionOption[] =>
  (intent.scenarios as AssetScanAction[])
    .concat(intent.inventory_task ? (['INVENTORY'] as AssetScanAction[]) : [])
    .map((action) => actionOptions[action])

export const assetScanActionMeta = (action: AssetScanAction): AssetScanActionOption =>
  actionOptions[action]

const actionPurposes: Record<AssetScanAction, AssetScanPurpose> = {
  PERSONAL_USE: 'USE',
  PERSONAL_BORROW: 'BORROW',
  PUBLIC_USE: 'USE',
  PUBLIC_BORROW: 'BORROW',
  PERSONAL_RETURN: 'RETURN',
  PUBLIC_RETURN: 'RETURN',
  INVENTORY: 'INVENTORY',
}

export const selectScanAction = (
  intent: AssetScanIntent,
  preferred?: AssetScanAction,
  preferredPurpose?: AssetScanPurpose,
): AssetScanAction | undefined => {
  const actions = assetScanActionOptions(intent).map((action) => action.value)
  if (preferred && actions.includes(preferred)) return preferred
  return actions.find((action) => actionPurposes[action] === preferredPurpose) ?? actions[0]
}
