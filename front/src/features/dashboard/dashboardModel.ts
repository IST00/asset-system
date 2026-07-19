import type { AssetMetrics, DashboardIssues, InventorySummary, PrimaryMetric } from './types.ts'

export function calculateProgress(inventory: InventorySummary): number {
  if (inventory.total <= 0) return 0
  const percentage = Math.round((inventory.checked / inventory.total) * 100)
  return Math.max(0, Math.min(percentage, 100))
}

export function countActionableIssues(issues: DashboardIssues): number {
  return (
    issues.pendingApprovals +
    issues.inventoryExceptions +
    issues.incompleteAssets +
    issues.departedOwnerAssets
  )
}

export function selectPrimaryMetrics(metrics: AssetMetrics): PrimaryMetric[] {
  return [
    { key: 'total', value: metrics.total },
    { key: 'idle', value: metrics.idle },
    { key: 'inUse', value: metrics.inUse },
    { key: 'repairing', value: metrics.repairing },
  ]
}
