import assert from 'node:assert/strict'
import test from 'node:test'
import { navigationEntries } from './navigation.ts'

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

test('marks exactly four destinations for mobile navigation', () => {
  assert.deepEqual(
    navigationEntries.filter((entry) => entry.mobile).map((entry) => entry.key),
    ['home', 'assets', 'inventory', 'profile'],
  )
})

test('enables every delivered business destination', () => {
  const assets = navigationEntries.find((entry) => entry.key === 'assets')

  assert.equal(assets?.permission, 'asset:view')
  assert.ok(navigationEntries.every((entry) => entry.disabled === undefined))
})
