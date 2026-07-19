import assert from 'node:assert/strict'
import test from 'node:test'
import { filterNavigation } from './navigationModel.ts'
import type { NavigationEntry } from './navigationModel.ts'

const entries: NavigationEntry[] = [
  { key: 'home', labelKey: 'nav.home', path: '/home', icon: 'home', mobile: true },
  { key: 'assets', labelKey: 'nav.assets', path: '/assets', icon: 'package', mobile: true },
  { key: 'inventory', labelKey: 'nav.inventory', path: '/inventory', icon: 'scan', mobile: true },
  { key: 'profile', labelKey: 'nav.profile', path: '/profile', icon: 'user', mobile: true },
  {
    key: 'permissions',
    labelKey: 'nav.permissions',
    path: '/permissions',
    icon: 'shield',
    permission: 'role:view',
  },
]

test('filters protected navigation by permission', () => {
  assert.deepEqual(
    filterNavigation(entries, new Set()).map((item) => item.key),
    ['home', 'assets', 'inventory', 'profile'],
  )
  assert.equal(filterNavigation(entries, new Set(['role:view'])).length, 5)
})

test('selects the four explicit mobile destinations', () => {
  assert.deepEqual(
    filterNavigation(entries, new Set(), true).map((item) => item.key),
    ['home', 'assets', 'inventory', 'profile'],
  )
})
