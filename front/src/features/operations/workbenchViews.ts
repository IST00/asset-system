import type { MyAsset } from '@/api/assetUsageReturn'
import type { OperationRequest } from '@/api/operations'

export type WorkflowView =
  | 'ALL'
  | 'PROCESSING'
  | 'CREATED_BY_ME'
  | 'ASSIGNED_TO_ME'
  | 'PENDING_MY_SIGN'
  | 'PENDING_MY_RETURN'
  | 'MY_IN_USE'
  | 'MY_BORROWED'
  | 'RECEIVED_HANDOVER'

export const workflowViewOptions: Array<{ label: string; value: WorkflowView }> = [
  { label: '全部', value: 'ALL' },
  { label: '处理中', value: 'PROCESSING' },
  { label: '我发起的申请', value: 'CREATED_BY_ME' },
  { label: '发给我的资产', value: 'ASSIGNED_TO_ME' },
  { label: '待我签收', value: 'PENDING_MY_SIGN' },
  { label: '待我归还', value: 'PENDING_MY_RETURN' },
  { label: '我的在用资产', value: 'MY_IN_USE' },
  { label: '我的借用资产', value: 'MY_BORROWED' },
  { label: '我收到的交接', value: 'RECEIVED_HANDOVER' },
]

const finalLabels = new Set(['已完成', '已拒绝', '已撤回', '已终止'])

export function filterWorkflowRecords(
  records: OperationRequest[],
  view: WorkflowView,
  currentUserId: number | undefined,
  statusLabel: (record: OperationRequest) => string,
): OperationRequest[] {
  if (view === 'ALL') return records
  if (view === 'PROCESSING') {
    return records.filter((record) => !finalLabels.has(statusLabel(record)))
  }
  if (view === 'CREATED_BY_ME') {
    return records.filter((record) => record.applicant_id === currentUserId)
  }
  if (view === 'ASSIGNED_TO_ME') {
    return records.filter(
      (record) =>
        record.operation_type === 'PERSONAL_USE' && record.target_user_id === currentUserId,
    )
  }
  if (view === 'PENDING_MY_SIGN') {
    return records.filter(
      (record) =>
        record.operation_type === 'PERSONAL_USE' &&
        record.target_user_id === currentUserId &&
        record.fulfillment_status === 'PENDING_SIGN',
    )
  }
  if (view === 'RECEIVED_HANDOVER') {
    return records.filter(
      (record) =>
        record.operation_type === 'TRANSFER' &&
        record.target_user_id === currentUserId &&
        record.execution_status === 'SUCCESS',
    )
  }
  return []
}

export function isMyAssetView(view: WorkflowView): boolean {
  return view === 'PENDING_MY_RETURN' || view === 'MY_IN_USE' || view === 'MY_BORROWED'
}

export function filterMyAssets(assets: MyAsset[], view: WorkflowView): MyAsset[] {
  if (view === 'MY_IN_USE') return assets.filter((asset) => asset.usage_mode === 'USE')
  if (view === 'PENDING_MY_RETURN' || view === 'MY_BORROWED') {
    return assets.filter((asset) => asset.usage_mode === 'BORROW')
  }
  return []
}
