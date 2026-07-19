export interface AssetMetrics {
  total: number
  idle: number
  inUse: number
  repairing: number
  scrapped: number
}

export interface DashboardIssues {
  pendingApprovals: number
  inventoryExceptions: number
  incompleteAssets: number
  departedOwnerAssets: number
}

export interface InventorySummary {
  taskName: string
  checked: number
  total: number
  exceptions: number
}

export interface CategoryDistribution {
  name: string
  value: number
  tone: DistributionTone
}

export type DistributionTone = 'brand' | 'success' | 'warning' | 'danger' | 'purple' | 'slate'

export interface StatusDistribution {
  key: 'idle' | 'inUse' | 'repairing' | 'pendingScrap' | 'scrapped'
  value: number
  tone: DistributionTone
}

export interface MonthlyChange {
  month: string
  intake: number
  scrapped: number
}

export interface DashboardOverview {
  metrics: AssetMetrics
  issues: DashboardIssues
  inventory: InventorySummary
  categories: CategoryDistribution[]
  statuses: StatusDistribution[]
  monthlyChanges: MonthlyChange[]
}

export interface PrimaryMetric {
  key: keyof Pick<AssetMetrics, 'total' | 'idle' | 'inUse' | 'repairing'>
  value: number
}
