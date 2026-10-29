import assert from 'node:assert/strict'
import test from 'node:test'
import { navigationEntries } from './navigation.ts'
import { filterNavigation } from './navigationModel.ts'

test('defines the business modules from the asset system plan', () => {
  assert.deepEqual(
    navigationEntries.filter((entry) => entry.key !== 'profile').map((entry) => entry.key),
    [
      'home',
      'assets',
      'workflows',
      'inventory',
      'approvals',
      'imports',
      'masterData',
      'permissions',
      'logs',
    ],
  )
})

test('selects employee and administrator destinations for mobile navigation', () => {
  const employeeNavigation = filterNavigation(navigationEntries, new Set(), true)
  const administratorNavigation = filterNavigation(navigationEntries, new Set(['asset:edit']), true)

  assert.deepEqual(
    employeeNavigation.map((entry) => entry.key),
    ['home', 'workflows', 'inventory', 'profile'],
  )
  assert.deepEqual(
    administratorNavigation.map((entry) => entry.key),
    ['home', 'assets', 'workflows', 'profile'],
  )
})

test('enables every delivered business destination', () => {
  const assets = navigationEntries.find((entry) => entry.key === 'assets')

  assert.equal(assets?.permission, 'asset:view')
  assert.ok(navigationEntries.every((entry) => entry.disabled === undefined))
})
