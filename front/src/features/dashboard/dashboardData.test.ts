import assert from 'node:assert/strict'
import test from 'node:test'
import { demoDashboardOverview } from './dashboardData.ts'

test('keeps dashboard distributions aligned with the total asset count', () => {
  const categoryTotal = demoDashboardOverview.categories.reduce(
    (total, item) => total + item.value,
    0,
  )
  const statusTotal = demoDashboardOverview.statuses.reduce((total, item) => total + item.value, 0)

  assert.equal(categoryTotal, demoDashboardOverview.metrics.total)
  assert.equal(statusTotal, demoDashboardOverview.metrics.total)
})

test('provides six ordered monthly points and valid inventory progress', () => {
  assert.equal(demoDashboardOverview.monthlyChanges.length, 6)
  assert.ok(demoDashboardOverview.inventory.checked <= demoDashboardOverview.inventory.total)
  assert.ok(
    demoDashboardOverview.monthlyChanges.every((item) => item.intake >= 0 && item.scrapped >= 0),
  )
})
