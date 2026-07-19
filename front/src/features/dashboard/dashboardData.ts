import type { DashboardOverview } from './types.ts'

export const demoDashboardOverview: DashboardOverview = {
  metrics: {
    total: 156,
    idle: 42,
    inUse: 98,
    repairing: 8,
    scrapped: 3,
  },
  issues: {
    pendingApprovals: 4,
    inventoryExceptions: 3,
    incompleteAssets: 12,
    departedOwnerAssets: 2,
  },
  inventory: {
    taskName: '2026 年第三季度资产盘点',
    checked: 90,
    total: 120,
    exceptions: 3,
  },
  categories: [
    { name: '电脑设备', value: 52, tone: 'brand' },
    { name: '移动设备', value: 38, tone: 'success' },
    { name: '显示设备', value: 24, tone: 'warning' },
    { name: '办公设备', value: 20, tone: 'purple' },
    { name: '会议设备', value: 12, tone: 'danger' },
    { name: '其他', value: 10, tone: 'slate' },
  ],
  statuses: [
    { key: 'idle', value: 42, tone: 'success' },
    { key: 'inUse', value: 98, tone: 'brand' },
    { key: 'repairing', value: 8, tone: 'danger' },
    { key: 'pendingScrap', value: 5, tone: 'warning' },
    { key: 'scrapped', value: 3, tone: 'slate' },
  ],
  monthlyChanges: [
    { month: '2月', intake: 8, scrapped: 1 },
    { month: '3月', intake: 12, scrapped: 2 },
    { month: '4月', intake: 15, scrapped: 3 },
    { month: '5月', intake: 10, scrapped: 2 },
    { month: '6月', intake: 14, scrapped: 4 },
    { month: '7月', intake: 12, scrapped: 3 },
  ],
}

export function getDemoDashboardOverview(): Promise<DashboardOverview> {
  return Promise.resolve(demoDashboardOverview)
}
