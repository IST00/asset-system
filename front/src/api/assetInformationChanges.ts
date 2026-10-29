import http from '@/api/http'

export type InformationChangeType = 'PHYSICAL' | 'FINANCIAL' | 'WARRANTY'
export type InformationChangeApprovalChannel = 'INTERNAL' | 'FEISHU'
export type InformationChangeValue = string | number | boolean | null

export interface InformationChangeItem {
  asset_id: number
  version: number
  changes: Record<string, string | number | null>
}

export interface InformationChangeAssetSnapshot {
  asset_id: number
  asset_code: string | null
  asset_name: string
  asset_status: string
  asset_version: number
  organization_id: number
  before_data: Record<string, InformationChangeValue>
  target_data: Record<string, InformationChangeValue>
}

export interface InformationChangeApprovalTask {
  id: number
  approver_id: number
  status: string
  opinion?: string | null
}

export interface InformationChangeApprovalStep {
  id: number
  level_no: number
  status: string
  tasks: InformationChangeApprovalTask[]
}

export interface InformationChangeRequest {
  id: number
  request_no: string
  operation_type: string
  change_request_id: number
  change_type: InformationChangeType
  reason: string
  applicant_id: number
  approval_channel: InformationChangeApprovalChannel
  requires_feishu_approval: boolean
  external_instance_id?: string | null
  approval_status: string
  execution_status: string
  executed_at?: string | null
  created_at?: string | null
  assets: InformationChangeAssetSnapshot[]
  approval_timeline: InformationChangeApprovalStep[]
}

export const assetInformationChangeApi = {
  submit(payload: {
    change_type: InformationChangeType
    items: InformationChangeItem[]
    reason: string
    idempotency_key?: string
  }) {
    return http.post<unknown, InformationChangeRequest>(
      '/asset-information-change-requests',
      payload,
    )
  },
  detail(operationRequestId: number) {
    return http.get<unknown, InformationChangeRequest>(
      `/asset-information-change-requests/${operationRequestId}`,
    )
  },
}
