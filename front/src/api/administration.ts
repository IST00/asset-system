import http from '@/api/http'
import type { User } from '@/types'

export interface ReferenceItem {
  id: number
  code: string
  name: string
  status: string
  version: number
}

export interface TreeItem extends ReferenceItem {
  children?: TreeItem[]
}

export interface SupplierItem extends ReferenceItem {
  contact_name?: string | null
  contact_phone?: string | null
}

export interface RoleItem {
  id: number
  code: string
  name: string
  data_scope: string
  built_in: boolean
  enabled: boolean
  version: number
  permissions: string[]
  organization_ids: number[]
}

export interface PermissionItem {
  id: number
  code: string
  name: string
  module: string
  enabled: boolean
}

export interface AuditLogItem {
  id: number
  action: string
  resource_type: string
  resource_id?: number | null
  operator_id: number
  before_data?: Record<string, unknown> | null
  after_data?: Record<string, unknown> | null
  reason?: string | null
  created_at: string
}

export const masterDataApi = {
  units: () => http.get<unknown, ReferenceItem[]>('/units'),
  sources: () => http.get<unknown, ReferenceItem[]>('/asset-sources'),
  locations: () => http.get<unknown, TreeItem[]>('/locations/tree'),
  categories: () => http.get<unknown, TreeItem[]>('/asset-categories/tree'),
  suppliers: () => http.get<unknown, SupplierItem[]>('/suppliers'),
  organizations: () => http.get<unknown, TreeItem[]>('/organizations/tree'),
}

export const administrationApi = {
  roles: () => http.get<unknown, RoleItem[]>('/roles'),
  permissions: () => http.get<unknown, PermissionItem[]>('/permissions'),
  users: (page = 0, size = 100) =>
    http.get<unknown, { items: User[]; total: number; page: number; size: number }>('/users', {
      params: { page, size },
    }),
  auditLogs: () => http.get<unknown, AuditLogItem[]>('/audit-logs'),
}
