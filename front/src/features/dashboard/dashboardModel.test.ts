import assert from 'node:assert/strict'
import test from 'node:test'
import { calculateProgress, countActionableIssues, selectPrimaryMetrics } from './dashboardModel.ts'
import type { DashboardOverview } from './types.ts'

const overview: DashboardOverview = {
  metrics: { total: 156, idle: 42, inUse: 98, repairing: 8, scrapped: 5 },
  issues: {
    pendingApprovals: 4,
    inventoryExceptions: 3,
    incompleteAssets: 12,
    departedOwnerAssets: 2,
  },
  inventory: {
    taskName: '2026 Q3 资产盘点',
    checked: 90,
    total: 120,
    exceptions: 3,
  },
  categories: [],
  statuses: [],
  monthlyChanges: [],
}

test('derives stable dashboard values', () => {
  assert.equal(calculateProgress(overview.inventory), 75)
  assert.equal(countActionableIssues(overview.issues), 21)
  assert.deepEqual(
    selectPrimaryMetrics(overview.metrics).map((metric) => metric.key),
    ['total', 'idle', 'inUse', 'repairing'],
  )
})

test('clamps invalid progress values', () => {
  assert.equal(calculateProgress({ taskName: 'empty', checked: 5, total: 0, exceptions: 0 }), 0)
  assert.equal(
    calculateProgress({ taskName: 'overflow', checked: 20, total: 10, exceptions: 0 }),
    100,
  )
})
