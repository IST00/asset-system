import assert from 'node:assert/strict'
import test from 'node:test'
import { filterNavigation } from './navigationModel.ts'
import type { NavigationEntry } from './navigationModel.ts'

const entries: NavigationEntry[] = [
  { key: 'home', labelKey: 'nav.home', path: '/home', icon: 'home', mobile: true },
  {
    key: 'assets',
    labelKey: 'nav.assets',
    path: '/assets',
    icon: 'package',
    mobile: true,
    mobilePermission: 'asset:edit',
    permission: 'asset:view',
  },
  {
    key: 'workflows',
    labelKey: 'nav.workflows',
    path: '/workflows',
    icon: 'workflow',
    mobile: true,
  },
  {
    key: 'inventory',
    labelKey: 'nav.inventory',
    path: '/inventory',
    icon: 'scan',
    mobile: true,
    mobileUnlessPermission: 'asset:edit',
  },
  { key: 'profile', labelKey: 'nav.profile', path: '/profile', icon: 'user', mobile: true },
  {
    key: 'approvals',
    labelKey: 'nav.approvals',
    path: '/approvals',
    icon: 'approval',
    permission: 'approval:task:view',
  },
  {
    key: 'imports',
    labelKey: 'nav.imports',
    path: '/imports',
    icon: 'import',
    permission: 'asset:import',
  },
  {
    key: 'masterData',
    labelKey: 'nav.masterData',
    path: '/master-data',
    icon: 'database',
    permission: 'organization:manage',
  },
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
    ['home', 'workflows', 'inventory', 'profile'],
  )
  assert.equal(filterNavigation(entries, new Set(['role:view'])).length, 5)
})

test('selects mobile destinations by role capability', () => {
  assert.deepEqual(
    filterNavigation(entries, new Set(), true).map((item) => item.key),
    ['home', 'workflows', 'inventory', 'profile'],
  )
  assert.deepEqual(
    filterNavigation(entries, new Set(['asset:edit']), true).map((item) => item.key),
    ['home', 'assets', 'workflows', 'profile'],
  )
})
