import assert from 'node:assert/strict'
import test from 'node:test'
import type { DashboardOverviewResponse } from '@/api/dashboard'
import { mapDashboardOverview } from './dashboardData.ts'

const backendOverview: DashboardOverviewResponse = {
  metrics: { total: 2, idle: 1, in_use: 1, repairing: 0, scrapped: 0 },
  issues: {
    pending_approvals: 0,
    inventory_exceptions: 0,
    incomplete_assets: 1,
    departed_owner_assets: 1,
  },
  inventory: {
    task_name: '暂无进行中的盘点任务',
    checked: 0,
    total: 0,
    exceptions: 0,
  },
  categories: [{ name: '电脑', value: 2 }],
  statuses: [
    { status: 'IDLE', value: 1 },
    { status: 'PENDING_RECEIPT', value: 0 },
    { status: 'IN_USE', value: 1 },
    { status: 'REPAIRING', value: 0 },
    { status: 'SCRAPPED', value: 0 },
  ],
  monthly_changes: [{ month: '2026-07', intake: 2, scrapped: 0 }],
}

test('maps backend dashboard fields without introducing demo values', () => {
  const overview = mapDashboardOverview(backendOverview)

  assert.deepEqual(overview.metrics, {
    total: 2,
    idle: 1,
    inUse: 1,
    repairing: 0,
    scrapped: 0,
  })
  assert.equal(overview.issues.incompleteAssets, 1)
  assert.equal(overview.categories[0]?.name, '电脑')
  assert.equal(overview.categories[0]?.value, 2)
  assert.equal(overview.monthlyChanges[0]?.month, '7月')
  assert.equal(
    overview.statuses.reduce((total, item) => total + item.value, 0),
    2,
  )
})

test('keeps a real empty backend response empty', () => {
  const overview = mapDashboardOverview({
    ...backendOverview,
    metrics: { total: 0, idle: 0, in_use: 0, repairing: 0, scrapped: 0 },
    issues: {
      pending_approvals: 0,
      inventory_exceptions: 0,
      incomplete_assets: 0,
      departed_owner_assets: 0,
    },
    categories: [],
    statuses: backendOverview.statuses.map((item) => ({ ...item, value: 0 })),
    monthly_changes: backendOverview.monthly_changes.map((item) => ({
      ...item,
      intake: 0,
      scrapped: 0,
    })),
  })

  assert.equal(overview.metrics.total, 0)
  assert.deepEqual(overview.categories, [])
  assert.ok(overview.statuses.every((item) => item.value === 0))
  assert.ok(overview.monthlyChanges.every((item) => item.intake === 0 && item.scrapped === 0))
})
