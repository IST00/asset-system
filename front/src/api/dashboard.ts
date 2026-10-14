import http from '@/api/http'

export interface DashboardMetricsResponse {
  total: number
  idle: number
  in_use: number
  repairing: number
  scrapped: number
}

export interface DashboardIssuesResponse {
  pending_approvals: number
  inventory_exceptions: number
  incomplete_assets: number
  departed_owner_assets: number
}

export interface DashboardInventoryResponse {
  task_name: string
  checked: number
  total: number
  exceptions: number
}

export interface DashboardCategoryResponse {
  name: string
  value: number
}

export interface DashboardStatusResponse {
  status: 'IDLE' | 'PENDING_RECEIPT' | 'IN_USE' | 'REPAIRING' | 'SCRAPPED'
  value: number
}

export interface DashboardMonthlyChangeResponse {
  month: string
  intake: number
  scrapped: number
}

export interface DashboardOverviewResponse {
  metrics: DashboardMetricsResponse
  issues: DashboardIssuesResponse
  inventory: DashboardInventoryResponse
  categories: DashboardCategoryResponse[]
  statuses: DashboardStatusResponse[]
  monthly_changes: DashboardMonthlyChangeResponse[]
}

export const dashboardApi = {
  overview: () => http.get<unknown, DashboardOverviewResponse>('/assets/dashboard'),
}
