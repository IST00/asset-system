import assert from 'node:assert/strict'
import test from 'node:test'
import {
  approvalRecords,
  auditLogs,
  importJobs,
  inventoryTasks,
  masterDataGroups,
  roleRecords,
  workflowRecords,
} from './data.ts'

test('provides demo data for every delivered operations page', () => {
  assert.ok(workflowRecords.length >= 5)
  assert.ok(inventoryTasks.length >= 3)
  assert.ok(approvalRecords.length >= 4)
  assert.ok(importJobs.length >= 3)
  assert.equal(masterDataGroups.length, 6)
  assert.equal(roleRecords.length, 4)
  assert.ok(auditLogs.length >= 5)
})

test('keeps inventory progress within valid task boundaries', () => {
  for (const task of inventoryTasks) {
    assert.ok(task.total > 0)
    assert.ok(task.checked >= 0)
    assert.ok(task.checked <= task.total)
    assert.ok(task.exceptions >= 0)
  }
})

test('uses unique stable identifiers across operational records', () => {
  const identifiers = [
    ...workflowRecords.map((record) => record.id),
    ...inventoryTasks.map((task) => task.id),
    ...approvalRecords.map((record) => record.id),
    ...importJobs.map((job) => job.id),
    ...auditLogs.map((log) => log.id),
  ]
  assert.equal(new Set(identifiers).size, identifiers.length)
})
