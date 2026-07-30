import type { User } from '@/types'

export const demoCredentials = Object.freeze({
  username: 'admin',
  password: 'admin123',
})

export const demoPermissions = Object.freeze([
  'asset:view',
  'asset:create',
  'asset:amount:view',
  'asset:import',
  'asset:label:print',
  'inventory:create',
  'role:view',
  'log:view',
])

export const demoUser: User = Object.freeze({
  id: 1,
  username: 'demo-admin',
  nickname: '资产管理员',
  role: '系统管理员',
  roles: ['SYSTEM_ADMIN'],
  permissions: [...demoPermissions],
})

export const demoToken = 'asset-system-local-demo-token'

export function isDemoLoginEnabled(value: string | undefined): boolean {
  return value === 'true'
}

export function isDemoCredentials(values: { username: string; password: string }): boolean {
  return (
    values.username === demoCredentials.username && values.password === demoCredentials.password
  )
}
