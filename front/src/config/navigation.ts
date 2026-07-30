import type { NavigationEntry } from './navigationModel.ts'

export const navigationEntries: NavigationEntry[] = [
  { key: 'home', labelKey: 'nav.home', path: '/home', icon: 'home', mobile: true },
  {
    key: 'assets',
    labelKey: 'nav.assets',
    path: '/assets',
    icon: 'package',
    mobile: true,
    permission: 'asset:view',
  },
  {
    key: 'workflows',
    labelKey: 'nav.workflows',
    path: '/workflows',
    icon: 'workflow',
  },
  {
    key: 'inventory',
    labelKey: 'nav.inventory',
    path: '/inventory',
    icon: 'scan',
    mobile: true,
  },
  {
    key: 'approvals',
    labelKey: 'nav.approvals',
    path: '/approvals',
    icon: 'approval',
  },
  {
    key: 'imports',
    labelKey: 'nav.imports',
    path: '/imports',
    icon: 'import',
  },
  {
    key: 'masterData',
    labelKey: 'nav.masterData',
    path: '/master-data',
    icon: 'database',
  },
  {
    key: 'permissions',
    labelKey: 'nav.permissions',
    path: '/permissions',
    icon: 'shield',
    permission: 'system:role:view',
  },
  {
    key: 'logs',
    labelKey: 'nav.logs',
    path: '/logs',
    icon: 'logs',
    permission: 'audit:view',
  },
  {
    key: 'profile',
    labelKey: 'nav.profile',
    path: '/profile',
    icon: 'user',
    mobile: true,
  },
]
