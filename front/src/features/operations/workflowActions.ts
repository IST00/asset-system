import type { OperationRequest } from '@/api/operations'

export interface LocalFeishuDecisionRecord {
  operation_type: string
  approval_status: string
  fulfillment_status?: string | null
  external_instance_id?: string | null
}

const localFeishuDecisionOperationTypes = new Set([
  'PERSONAL_USE',
  'PUBLIC_USE',
  'PERSONAL_RETURN',
  'PUBLIC_RETURN',
])

const internalDecisionOperationTypes = new Set([
  'PERSONAL_USE',
  'PUBLIC_USE',
  'PERSONAL_RETURN',
  'PUBLIC_RETURN',
  'PHYSICAL_INFO_CHANGE',
  'FINANCIAL_INFO_CHANGE',
  'WARRANTY_INFO_CHANGE',
])

export function canHandleLocalFeishuDecision(
  record: LocalFeishuDecisionRecord,
  canManageUsage: boolean,
): boolean {
  const isPendingPersonalIssue =
    record.operation_type === 'PERSONAL_USE' && record.fulfillment_status === 'PENDING_ISSUE'
  return (
    canManageUsage &&
    localFeishuDecisionOperationTypes.has(record.operation_type) &&
    record.approval_status === 'PENDING' &&
    !isPendingPersonalIssue &&
    Boolean(record.external_instance_id?.startsWith('LOCAL-FEISHU-'))
  )
}

export function canHandleInternalDecision(
  record: Pick<OperationRequest, 'operation_type' | 'approval_status' | 'approval_channel'>,
  canManageUsage: boolean,
): boolean {
  return (
    canManageUsage &&
    internalDecisionOperationTypes.has(record.operation_type) &&
    record.approval_status === 'PENDING' &&
    record.approval_channel === 'INTERNAL'
  )
}
