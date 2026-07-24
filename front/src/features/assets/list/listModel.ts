import {
  canCreateAsset,
  canViewAmount,
  getAssetStatusMeta,
  getOrderedAssetStatuses,
  parseAssetCodes,
} from '../assetModel.ts'
import type { AssetStatusMeta } from '../assetModel.ts'
import type { AssetListQuery, AssetStatus, AssetSummary } from '../types.ts'

export type AssetColumnKey = Exclude<keyof AssetSummary, 'id'>
export { canCreateAsset }

export interface AssetListFilterValues {
  keyword?: string
  assetCodesText?: string
  company_name?: string
  category_name?: string
  status?: AssetStatus
  department_name?: string
  location_name?: string
  information_complete?: boolean
  user_name?: string
  manager_name?: string
  supplier_name?: string
  source_name?: string
  purchase_date_from?: string
  purchase_date_to?: string
}

export interface AssetStatusOption {
  readonly value: AssetStatus
  readonly meta: AssetStatusMeta
}

const availableColumns: AssetColumnKey[] = [
  'asset_code',
  'asset_name',
  'category_name',
  'status',
  'model',
  'serial_number',
  'receipt_number',
  'user_name',
  'department_name',
  'location_name',
  'manager_name',
  'company_name',
  'supplier_name',
  'source_name',
  'unit_name',
  'purchase_date',
  'purchase_amount',
  'information_complete',
]

const desktopDefaultColumns: AssetColumnKey[] = [
  'asset_code',
  'asset_name',
  'category_name',
  'status',
  'user_name',
  'department_name',
  'location_name',
  'manager_name',
  'company_name',
  'purchase_date',
]

const mobileDefaultColumns: AssetColumnKey[] = [
  'asset_code',
  'asset_name',
  'status',
  'category_name',
]

const trimOptional = (value: string | undefined): string | undefined => {
  const trimmed = value?.trim()
  return trimmed ? trimmed : undefined
}

export function buildAssetListQuery(
  filters: AssetListFilterValues,
  size: 20 | 50 | 100,
): AssetListQuery {
  const assetCodes = parseAssetCodes(filters.assetCodesText ?? '')
  const query: AssetListQuery = { page: 1, size }
  const keyword = trimOptional(filters.keyword)
  const companyName = trimOptional(filters.company_name)
  const categoryName = trimOptional(filters.category_name)
  const departmentName = trimOptional(filters.department_name)
  const locationName = trimOptional(filters.location_name)
  const userName = trimOptional(filters.user_name)
  const managerName = trimOptional(filters.manager_name)
  const supplierName = trimOptional(filters.supplier_name)
  const sourceName = trimOptional(filters.source_name)
  const purchaseDateFrom = trimOptional(filters.purchase_date_from)
  const purchaseDateTo = trimOptional(filters.purchase_date_to)

  if (keyword) query.keyword = keyword
  if (assetCodes.length > 0) query.asset_codes = assetCodes
  if (companyName) query.company_name = companyName
  if (categoryName) query.category_name = categoryName
  if (filters.status) query.status = filters.status
  if (departmentName) query.department_name = departmentName
  if (locationName) query.location_name = locationName
  if (filters.information_complete !== undefined) {
    query.information_complete = filters.information_complete
  }
  if (userName) query.user_name = userName
  if (managerName) query.manager_name = managerName
  if (supplierName) query.supplier_name = supplierName
  if (sourceName) query.source_name = sourceName
  if (purchaseDateFrom) query.purchase_date_from = purchaseDateFrom
  if (purchaseDateTo) query.purchase_date_to = purchaseDateTo

  return query
}

export function getAvailableColumns(permissions: string[] | undefined): AssetColumnKey[] {
  return availableColumns.filter(
    (column) => column !== 'purchase_amount' || canViewAmount(permissions),
  )
}

export function getNextQueryRevision(currentRevision: number): number {
  return currentRevision + 1
}

export function getAssetStatusOptions(): AssetStatusOption[] {
  return getOrderedAssetStatuses().map((status) => ({
    value: status,
    meta: getAssetStatusMeta(status),
  }))
}

export function getDefaultColumns(viewport: 'desktop' | 'mobile'): AssetColumnKey[] {
  return viewport === 'mobile' ? mobileDefaultColumns.slice() : desktopDefaultColumns.slice()
}
