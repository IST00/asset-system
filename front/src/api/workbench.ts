import http from '@/api/http'
import type { OperationRequest } from '@/api/operations'

export type WorkbenchView =
  | 'my-requests'
  | 'assigned-to-me'
  | 'pending-sign'
  | 'pending-return'
  | 'my-assets'
  | 'my-borrowed'
  | 'received-handovers'

export interface WorkbenchSummary {
  pending_approval: number
  pending_issue: number
  pending_sign: number
  pending_handover: number
  due_soon: number
  due_today: number
  overdue: number
  manager_requested_return: number
  return_processing: number
  pending_return_inspection: number
  my_in_use: number
  my_borrowed: number
}

export interface WorkbenchQuery {
  page: number
  size: number
  status?: string
  keyword?: string
  start_date?: string
  end_date?: string
  pending_only?: boolean
}

export interface WorkbenchUser {
  id: number
  name: string | null
}

export interface WorkbenchRequestAsset {
  asset_id: number
  asset_code: string | null
  asset_name: string
}

export interface WorkbenchRequest {
  id: number
  request_no: string
  operation_type: string
  applicant_id: number
  applicant: WorkbenchUser | null
  target_user_id: number | null
  target_user: WorkbenchUser | null
  approval_status: string
  execution_status: string
  display_status: string
  pending: boolean
  created_at: string
  submitted_at: string | null
  approved_at: string | null
  executed_at: string | null
  usage_mode: 'USE' | 'BORROW' | null
  expected_return_at: string | null
  fulfillment_status: string | null
  requested_category: { id: number; code: string; name: string } | null
  requested_quantity: number | null
  reason: string | null
  assets: WorkbenchRequestAsset[]
}

export type ReturnState =
  | 'NOT_BORROWED'
  | 'NORMAL'
  | 'DUE_SOON'
  | 'DUE_TODAY'
  | 'OVERDUE'
  | 'MANAGER_REQUESTED'
  | 'RETURN_PROCESSING'
  | 'PENDING_INSPECTION'

export interface WorkbenchAsset {
  id: number
  asset_code: string
  asset_name: string
  status: 'IN_USE'
  display_status: 'IN_USE' | 'BORROWED'
  location_id: number | null
  usage_mode: 'USE' | 'BORROW'
  expected_return_at: string | null
  return_state: ReturnState
  usage_request_id: number | null
  return_request_id: number | null
  return_request_no: string | null
  return_requested_at: string | null
  return_request_reason: string | null
  return_handed_over_at: string | null
}

export interface WorkbenchPage<Item> {
  items: Item[]
  total: number
  page: number
  size: number
  pending_count: number
}

export interface WorkbenchTimelineAttachment {
  id: number
  asset_id: number
  business_type: string
  document_type: string
  original_name: string
  size_bytes: number
  uploaded_by: WorkbenchUser | null
  created_at: string | null
}

export interface WorkbenchTimelineEvent {
  key: string
  title: string
  actor: WorkbenchUser | null
  occurred_at: string | null
  remark: string | null
  status: string
  asset_codes: string[]
  approval_result: string | null
  rejection_reason: string | null
  attachments: WorkbenchTimelineAttachment[]
}

export interface WorkbenchRequestDetail extends OperationRequest {
  display_status: string
  current_handler: { role: string; users: Array<WorkbenchUser | null> } | null
  next_step: string
  available_actions: string[]
  timeline: WorkbenchTimelineEvent[]
}

const requestPage = (view: WorkbenchView, params: WorkbenchQuery) =>
  http.get<unknown, WorkbenchPage<WorkbenchRequest>>(`/workbench/${view}`, { params })

const assetPage = (view: 'pending-return' | 'my-assets' | 'my-borrowed', params: WorkbenchQuery) =>
  http.get<unknown, WorkbenchPage<WorkbenchAsset>>(`/workbench/${view}`, { params })

export const workbenchApi = {
  summary: () => http.get<unknown, WorkbenchSummary>('/workbench/summary'),
  requests: requestPage,
  assets: assetPage,
  detail: (id: number) => http.get<unknown, WorkbenchRequestDetail>(`/workbench/requests/${id}`),
}
