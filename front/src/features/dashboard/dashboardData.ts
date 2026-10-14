import type { DashboardOverviewResponse } from '@/api/dashboard'
import type { DashboardOverview, DistributionTone, StatusDistribution } from './types.ts'

const categoryTones: DistributionTone[] = [
  'brand',
  'success',
  'warning',
  'purple',
  'danger',
  'slate',
]

const statusPresentation: Record<
  DashboardOverviewResponse['statuses'][number]['status'],
  Pick<StatusDistribution, 'key' | 'tone'>
> = {
  IDLE: { key: 'idle', tone: 'success' },
  PENDING_RECEIPT: { key: 'pendingReceipt', tone: 'warning' },
  IN_USE: { key: 'inUse', tone: 'brand' },
  REPAIRING: { key: 'repairing', tone: 'danger' },
  SCRAPPED: { key: 'scrapped', tone: 'slate' },
}

function formatMonth(month: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(month)
  return match ? `${Number(match[2])}月` : month
}

export function mapDashboardOverview(response: DashboardOverviewResponse): DashboardOverview {
  return {
    metrics: {
      total: response.metrics.total,
      idle: response.metrics.idle,
      inUse: response.metrics.in_use,
      repairing: response.metrics.repairing,
      scrapped: response.metrics.scrapped,
    },
    issues: {
      pendingApprovals: response.issues.pending_approvals,
      inventoryExceptions: response.issues.inventory_exceptions,
      incompleteAssets: response.issues.incomplete_assets,
      departedOwnerAssets: response.issues.departed_owner_assets,
    },
    inventory: {
      taskName: response.inventory.task_name,
      checked: response.inventory.checked,
      total: response.inventory.total,
      exceptions: response.inventory.exceptions,
    },
    categories: response.categories.map((item, index) => ({
      ...item,
      tone: categoryTones[index % categoryTones.length],
    })),
    statuses: response.statuses.map((item) => ({
      ...statusPresentation[item.status],
      value: item.value,
    })),
    monthlyChanges: response.monthly_changes.map((item) => ({
      month: formatMonth(item.month),
      intake: item.intake,
      scrapped: item.scrapped,
    })),
  }
}
