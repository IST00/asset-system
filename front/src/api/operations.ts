import http from '@/api/http'

export interface OperationAssetSnapshot {
  asset_id: number
  asset_code: string
  asset_name: string
  asset_status: string
}

export interface OperationRequest {
  id: number
  request_no: string
  operation_type: string
  applicant_id: number
  approval_status: string
  execution_status: string
  execution_error?: string | null
  assets: OperationAssetSnapshot[]
  termination_reason?: string | null
  last_reminded_at?: string | null
  next_remind_at?: string | null
}

export interface OperationPage {
  items: OperationRequest[]
  total: number
  page: number
  size: number
}

export interface ApprovalTask {
  id: number
  operation_request_id: number
  request_no: string
  operation_type: string
  level_no: number
  status: string
  version: number
  approver_id?: number
}

export interface ApprovalCandidate {
  id: number
  username: string
  nickname: string | null
  organization_id: number | null
}

export interface ApprovalEvent {
  id: number
  operation_request_id: number
  approval_task_id: number | null
  actor_id: number
  event_type: 'TRANSFER' | 'REMIND'
  from_approver_id: number | null
  to_approver_id: number | null
  reason: string
  created_at: string
}

export interface ReminderResult {
  operation_request_id: number
  event_id: number
  channel: 'SYSTEM'
  reminded_at: string
  next_allowed_at: string
}

export const operationApi = {
  list: (page = 0, size = 50) =>
    http.get<unknown, OperationPage>('/operation-requests', { params: { page, size } }),
  detail: (id: number) => http.get<unknown, OperationRequest>(`/operation-requests/${id}`),
  myTasks: () => http.get<unknown, ApprovalTask[]>('/approval-tasks/my'),
  approve: (taskId: number, opinion?: string) =>
    http.post<unknown, OperationRequest>(`/approval-tasks/${taskId}/approve`, { opinion }),
  reject: (taskId: number, opinion: string) =>
    http.post<unknown, OperationRequest>(`/approval-tasks/${taskId}/reject`, { opinion }),
  transferCandidates: (taskId: number) =>
    http.get<unknown, ApprovalCandidate[]>(`/approval-tasks/${taskId}/transfer-candidates`),
  transfer: (taskId: number, toApproverId: number, taskVersion: number, reason: string) =>
    http.post<unknown, ApprovalTask>(`/approval-tasks/${taskId}/transfer`, {
      to_approver_id: toApproverId,
      task_version: taskVersion,
      reason,
    }),
  remind: (operationRequestId: number, reason: string) =>
    http.post<unknown, ReminderResult>(`/operation-requests/${operationRequestId}/remind`, {
      reason,
    }),
  approvalEvents: (operationRequestId: number) =>
    http.get<unknown, ApprovalEvent[]>(`/operation-requests/${operationRequestId}/approval-events`),
}
