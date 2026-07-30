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
}
