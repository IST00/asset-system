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
  parent_id?: number | null
  is_selectable?: boolean
  service_life_months?: number
  default_unit_id?: number
  children?: TreeItem[]
}

export interface SupplierItem extends ReferenceItem {
  unified_social_credit_code?: string | null
  contact_name?: string | null
  contact_phone?: string | null
  address?: string | null
  remark?: string | null
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

export interface SecurityEventItem {
  id: number
  event_type: string
  user_id?: number | null
  username?: string | null
  ip_address?: string | null
  detail?: string | null
  created_at: string
}

export interface SecurityEventPage {
  items: SecurityEventItem[]
  total: number
  page: number
  size: number
}

export interface DeleteImpactReference {
  key: string
  label: string
  count: number
}

export interface DeleteImpact {
  entity_id?: number
  role_id?: number
  code?: string
  role_code?: string
  name?: string
  role_name?: string
  version: number
  can_delete: boolean
  blockers: string[]
  references: DeleteImpactReference[]
}

export interface DeleteRequest {
  version: number
  reason: string
  confirmed: true
}

export interface ReferencePayload {
  code: string
  name: string
}

export interface LocationPayload {
  name: string
  parent_id?: number | null
  is_selectable: boolean
}

export interface CategoryPayload extends ReferencePayload {
  parent_id?: number | null
  service_life_months: number
  default_unit_id: number
}

export interface SupplierPayload {
  name: string
  unified_social_credit_code?: string | null
  contact_name?: string | null
  contact_phone?: string | null
  address?: string | null
  remark?: string | null
}

export const masterDataApi = {
  units: () => http.get<unknown, ReferenceItem[]>('/units'),
  createUnit: (payload: ReferencePayload) => http.post<unknown, ReferenceItem>('/units', payload),
  updateUnit: (id: number, payload: { name: string; version: number }) =>
    http.post<unknown, ReferenceItem>(`/units/${id}/update`, payload),
  setUnitEnabled: (id: number, enabled: boolean) =>
    http.post<unknown, ReferenceItem>(`/units/${id}/${enabled ? 'enable' : 'disable'}`),

  sources: () => http.get<unknown, ReferenceItem[]>('/asset-sources'),
  createSource: (payload: ReferencePayload) =>
    http.post<unknown, ReferenceItem>('/asset-sources', payload),
  updateSource: (id: number, payload: { name: string; version: number }) =>
    http.post<unknown, ReferenceItem>(`/asset-sources/${id}/update`, payload),
  setSourceEnabled: (id: number, enabled: boolean) =>
    http.post<unknown, ReferenceItem>(`/asset-sources/${id}/${enabled ? 'enable' : 'disable'}`),

  locations: () => http.get<unknown, TreeItem[]>('/locations/tree'),
  createLocation: (payload: LocationPayload) => http.post<unknown, TreeItem>('/locations', payload),
  updateLocation: (id: number, payload: LocationPayload & { version: number }) =>
    http.post<unknown, TreeItem>(`/locations/${id}/update`, payload),
  setLocationEnabled: (id: number, enabled: boolean) =>
    http.post<unknown, TreeItem>(`/locations/${id}/${enabled ? 'enable' : 'disable'}`),
  locationDeleteImpact: (id: number) =>
    http.get<unknown, DeleteImpact>(`/locations/${id}/delete-impact`),
  deleteLocation: (id: number, payload: DeleteRequest) =>
    http.post<unknown, { id: number; deleted: true }>(`/locations/${id}/delete`, payload),

  categories: () => http.get<unknown, TreeItem[]>('/asset-categories/tree'),
  createCategory: (payload: CategoryPayload) =>
    http.post<unknown, TreeItem>('/asset-categories', payload),
  updateCategory: (id: number, payload: Omit<CategoryPayload, 'code'> & { version: number }) =>
    http.post<unknown, TreeItem>(`/asset-categories/${id}/update`, payload),
  setCategoryEnabled: (id: number, enabled: boolean) =>
    http.post<unknown, TreeItem>(`/asset-categories/${id}/${enabled ? 'enable' : 'disable'}`),
  categoryDeleteImpact: (id: number) =>
    http.get<unknown, DeleteImpact>(`/asset-categories/${id}/delete-impact`),
  deleteCategory: (id: number, payload: DeleteRequest) =>
    http.post<unknown, { id: number; deleted: true }>(`/asset-categories/${id}/delete`, payload),

  suppliers: () => http.get<unknown, SupplierItem[]>('/suppliers'),
  createSupplier: (payload: SupplierPayload) =>
    http.post<unknown, SupplierItem>('/suppliers', payload),
  updateSupplier: (id: number, payload: SupplierPayload & { version: number }) =>
    http.post<unknown, SupplierItem>(`/suppliers/${id}/update`, payload),
  setSupplierEnabled: (id: number, enabled: boolean, version: number) =>
    http.post<unknown, SupplierItem>(`/suppliers/${id}/${enabled ? 'enable' : 'disable'}`, {
      version,
    }),

  organizations: () => http.get<unknown, TreeItem[]>('/organizations/tree'),
  createOrganization: (payload: ReferencePayload & { parent_id?: number | null }) =>
    http.post<unknown, TreeItem>('/organizations', payload),
  updateOrganization: (
    id: number,
    payload: { name: string; parent_id?: number | null; version: number },
  ) => http.post<unknown, TreeItem>(`/organizations/${id}/update`, payload),
  setOrganizationEnabled: (id: number, enabled: boolean) =>
    http.post<unknown, TreeItem>(`/organizations/${id}/${enabled ? 'enable' : 'disable'}`),
}

export const administrationApi = {
  roles: () => http.get<unknown, RoleItem[]>('/roles'),
  permissions: () => http.get<unknown, PermissionItem[]>('/permissions'),
  users: (page = 0, size = 100, keyword = '') =>
    http.get<unknown, { items: User[]; total: number; page: number; size: number }>('/users', {
      params: { page, size, keyword },
    }),
  auditLogs: () => http.get<unknown, AuditLogItem[]>('/audit-logs'),
  securityEvents: (page = 0, size = 100) =>
    http.get<unknown, SecurityEventPage>('/security-events', { params: { page, size } }),
  createRole: (payload: { code: string; name: string; data_scope: string; reason: string }) =>
    http.post<unknown, RoleItem>('/roles', payload),
  updateRole: (
    id: number,
    payload: {
      name: string
      data_scope: string
      enabled: boolean
      organization_ids: number[]
      version: number
      reason: string
    },
  ) => http.post<unknown, RoleItem>(`/roles/${id}/update`, payload),
  updateRolePermissions: (id: number, permissionIds: number[], reason: string) =>
    http.post<unknown, RoleItem>(`/roles/${id}/permissions/update`, {
      permission_ids: permissionIds,
      reason,
    }),
  updateUserRoles: (id: number, roleIds: number[], reason: string) =>
    http.post<unknown, User>(`/users/${id}/roles/update`, { role_ids: roleIds, reason }),
  roleDeleteImpact: (id: number) => http.get<unknown, DeleteImpact>(`/roles/${id}/delete-impact`),
  deleteRole: (id: number, payload: DeleteRequest) =>
    http.post<unknown, { id: number; deleted: true }>(`/roles/${id}/delete`, payload),
}
