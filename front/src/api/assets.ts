import http from '@/api/http'
import {
  administrationApi,
  masterDataApi,
  type ReferenceItem,
  type TreeItem,
} from '@/api/administration'
import type { AssetScanIntent } from '@/features/assets/scan/scanIntentModel'
import type { PageResult } from '@/types'
import type {
  AssetDetail,
  AssetListQuery,
  AssetPayload,
  AssetSummary,
} from '@/features/assets/types'

interface BackendPage<T> {
  items: T[]
  total: number
  page: number
  size: number
}

export interface AssetLifecycleRecord {
  id: number
  operation_type: string
  operation_no: string
  operator_id: number
  operator_name?: string | null
  before_data: Record<string, unknown> | null
  after_data: Record<string, unknown> | null
  remark?: string | null
  change_summary?: string | null
  created_at: string
}

import { mapBackendAsset, type BackendAsset } from '@/api/assetMapper'

const toSummary = (asset: AssetDetail): AssetSummary => asset

export async function listAssets(query: AssetListQuery): Promise<PageResult<AssetSummary>> {
  const params: Record<string, string | number> = {
    page: Math.max(0, query.page - 1),
    size: query.size,
  }
  const assignText = (key: keyof AssetListQuery) => {
    const value = query[key]
    if (typeof value === 'string' && value.trim()) params[key] = value.trim()
  }
  const textFilterKeys: Array<keyof AssetListQuery> = [
    'keyword',
    'company_name',
    'category_name',
    'status',
    'department_name',
    'location_name',
    'user_name',
    'manager_name',
    'supplier_name',
    'source_name',
    'purchase_date_from',
    'purchase_date_to',
  ]
  textFilterKeys.forEach(assignText)
  if (query.asset_codes?.length) params.asset_codes = query.asset_codes.join(',')
  if (query.information_complete !== undefined) {
    params.data_completeness = query.information_complete ? 'COMPLETE' : 'INCOMPLETE'
  }

  const result = await http.get<unknown, BackendPage<BackendAsset>>('/assets', { params })
  return {
    records: result.items.map(mapBackendAsset).map(toSummary),
    total: result.total,
    page: result.page + 1,
    size: result.size,
  }
}

export async function getAsset(assetId: number): Promise<AssetDetail> {
  try {
    const result = await http.get<unknown, BackendAsset>(`/assets/${assetId}`)
    return mapBackendAsset(result)
  } catch (error) {
    if (error instanceof Error && /not found|不存在/i.test(error.message)) {
      throw new Error('ASSET_NOT_FOUND')
    }
    throw error
  }
}

export function getAssetLifecycle(assetId: number): Promise<AssetLifecycleRecord[]> {
  return http.get<unknown, AssetLifecycleRecord[]>(`/assets/${assetId}/lifecycle`)
}

export interface AssetApprovalTaskRecord {
  id: number
  approver_id: number
  approver_name?: string | null
  status: string
  opinion?: string | null
  decided_at?: string | null
}

export interface AssetApprovalStepRecord {
  id: number
  level_no: number
  sign_mode: string
  status: string
  tasks: AssetApprovalTaskRecord[]
}

export interface AssetOperationRecord {
  id: number
  request_no: string
  operation_type: string
  applicant_id: number
  applicant_name?: string | null
  approval_channel: string
  approval_status: string
  execution_status: string
  submitted_at?: string | null
  approved_at?: string | null
  withdrawn_at?: string | null
  withdrawal_reason?: string | null
  executed_at?: string | null
  execution_error?: string | null
  before_data: Record<string, unknown>
  target_data: Record<string, unknown>
  approval_steps: AssetApprovalStepRecord[]
  created_at: string
}

export interface AssetInventoryRecord {
  id: number
  task_id: number
  task_no: string
  task_name: string
  task_status: string
  deadline_at: string
  item_status: string
  physical_result?: string | null
  location_result?: string | null
  ledger_location_name?: string | null
  actual_location_text?: string | null
  loss_reason?: string | null
  loss_description?: string | null
  borrowed_by?: string | null
  submission_method?: string | null
  submitted_by?: number | null
  submitted_by_name?: string | null
  submitted_at?: string | null
  is_late: boolean
  review_status: string
  resolution?: string | null
  resolution_reason?: string | null
  created_at: string
}

export interface AssetRelatedRecords {
  operations: AssetOperationRecord[]
  inventory_records: AssetInventoryRecord[]
}

export function getAssetRelatedRecords(assetId: number): Promise<AssetRelatedRecords> {
  return http.get<unknown, AssetRelatedRecords>(`/assets/${assetId}/related-records`)
}

export interface AssetUsageCandidate {
  id: number
  asset_code: string
  asset_name: string
  status: 'IDLE'
  category_id: number
  category_name: string
  organization_id: number
  organization_name: string
  location_id?: number | null
  location_name: string
}

export interface AssetReferenceData {
  organizations: TreeItem[]
  categories: TreeItem[]
  units: ReferenceItem[]
  sources: ReferenceItem[]
  locations: TreeItem[]
  suppliers: ReferenceItem[]
  managers: Array<{ id: number; name: string; enabled: boolean }>
  holders: Array<{
    id: number
    name: string
    enabled: boolean
    organization_id?: number | null
  }>
}

export interface StockInSubmitResult {
  id: number
  request_no: string
  approval_status: string
  execution_status: string
}

export interface StockInRequestItem {
  id: number
  asset_code: string
  asset_name: string
  category_id: number
  unit_id: number
  supplier_id?: number | null
  original_amount?: string
  zero_amount_reason?: string | null
  purchase_date: string
  service_life_months: number
  manager_id: number
  source_id: number
  location_id: number
  usage_company_id: number
  usage_department_id?: number | null
  holder_user_id?: number | null
  specification_model?: string | null
  serial_number?: string | null
  receipt_no?: string | null
  rfid_tag?: string | null
  remark?: string | null
  custom_attributes: Record<string, unknown>
}

export interface StockInRequestDetail extends StockInSubmitResult {
  parent_request_id?: number | null
  organization_id: number
  applicant_id: number
  remark?: string | null
  items: StockInRequestItem[]
}

const flattenTree = (items: TreeItem[]): TreeItem[] =>
  items.flatMap((item) => [item, ...flattenTree(item.children ?? [])])

const requireNamed = <T extends { id: number; name: string }>(
  items: T[],
  name: string | undefined,
  label: string,
): T => {
  const normalized = name?.trim()
  const item = items.find((candidate) => candidate.name === normalized)
  if (!item) throw new Error(`${label}已失效，请刷新页面后重新选择`)
  return item
}

const USER_PAGE_SIZE = 200

async function loadAllUsers() {
  const firstPage = await administrationApi.users(0, USER_PAGE_SIZE)
  const remainingPages = Math.ceil(firstPage.total / USER_PAGE_SIZE) - 1
  if (remainingPages <= 0) return firstPage.items

  const pages = await Promise.all(
    Array.from({ length: remainingPages }, (_, index) =>
      administrationApi.users((index + 1) * USER_PAGE_SIZE, USER_PAGE_SIZE),
    ),
  )
  return [...firstPage.items, ...pages.flatMap((page) => page.items)].filter(
    (user, index, users) => users.findIndex((candidate) => candidate.id === user.id) === index,
  )
}

export async function loadAssetReferences(): Promise<AssetReferenceData> {
  const [organizations, categories, units, sources, locations, suppliers, users] =
    await Promise.all([
      masterDataApi.organizations(),
      masterDataApi.categories(),
      masterDataApi.units(),
      masterDataApi.sources(),
      masterDataApi.locations(),
      masterDataApi.suppliers(),
      loadAllUsers(),
    ])
  return {
    organizations,
    categories,
    units,
    sources,
    locations,
    suppliers,
    managers: users.map((user) => ({
      id: user.id,
      name: user.nickname || user.username,
      enabled: user.enabled !== false,
    })),
    holders: users
      .filter((user) => user.enabled !== false && user.organization_id)
      .map((user) => ({
        id: user.id,
        name: user.nickname || user.username,
        enabled: user.enabled !== false,
        organization_id: user.organization_id ?? null,
      })),
  }
}

function buildStockInRequestPayload(payload: AssetPayload, references: AssetReferenceData) {
  const organizations = flattenTree(references.organizations)
  const categories = flattenTree(references.categories)
  const locations = flattenTree(references.locations)
  const organization = requireNamed(organizations, payload.company_name, '所属公司')
  const usageCompany = requireNamed(organizations, payload.usage_company_name, '使用公司')
  const usageDepartment = payload.usage_department_name
    ? requireNamed(organizations, payload.usage_department_name, '使用部门')
    : undefined
  const category = requireNamed(categories, payload.category_name, '资产分类')
  const unit = requireNamed(references.units, payload.unit_name, '计量单位')
  const source = requireNamed(references.sources, payload.source_name, '资产来源')
  const location = requireNamed(locations, payload.location_name, '存放地点')
  const manager = requireNamed(references.managers, payload.manager_name, '责任管理员')
  const holder = payload.holder_user_name
    ? requireNamed(references.holders, payload.holder_user_name, '使用人')
    : undefined
  const supplier = payload.supplier_name
    ? requireNamed(references.suppliers, payload.supplier_name, '供应商')
    : undefined

  return {
    organization_id: organization.id,
    remark: payload.remark,
    idempotency_key: crypto.randomUUID(),
    items: [
      {
        asset_name: payload.asset_name,
        category_id: category.id,
        unit_id: unit.id,
        original_amount: payload.purchase_amount.toFixed(2),
        zero_amount_reason: payload.zero_amount_reason,
        purchase_date: payload.purchase_date,
        supplier_id: supplier?.id,
        manager_id: manager.id,
        source_id: source.id,
        location_id: location.id,
        usage_company_id: usageCompany.id,
        usage_department_id: usageDepartment?.id ?? null,
        holder_user_id: holder?.id ?? null,
        specification_model: payload.model,
        serial_number: payload.serial_number,
        rfid_tag: payload.rfid_tag || undefined,
        remark: payload.remark,
        custom_attributes: {},
      },
    ],
  }
}

export function createAsset(
  payload: AssetPayload,
  references: AssetReferenceData,
): Promise<StockInSubmitResult> {
  return http.post<unknown, StockInSubmitResult>(
    '/stock-in-requests',
    buildStockInRequestPayload(payload, references),
  )
}

export function getStockInRequest(requestId: number): Promise<StockInRequestDetail> {
  return http.get<unknown, StockInRequestDetail>(`/stock-in-requests/${requestId}`)
}

export function resubmitAsset(
  parentRequestId: number,
  payload: AssetPayload,
  references: AssetReferenceData,
  original: StockInRequestDetail,
): Promise<StockInSubmitResult> {
  const reason = payload.change_reason?.trim()
  if (!reason) throw new Error('请填写重新提交说明')
  const requestPayload = buildStockInRequestPayload(payload, references)
  return http.post<unknown, StockInSubmitResult>(`/stock-in-requests/${parentRequestId}/resubmit`, {
    ...requestPayload,
    items: requestPayload.items.map((item, index) => ({
      ...item,
      service_life_months: original.items[index]?.service_life_months,
      receipt_no: original.items[index]?.receipt_no,
      custom_attributes: original.items[index]?.custom_attributes ?? {},
    })),
    resubmit_reason: reason,
  })
}

export async function updateAsset(
  assetId: number,
  payload: AssetPayload,
  current: AssetDetail,
  references: AssetReferenceData,
): Promise<AssetDetail> {
  const categories = flattenTree(references.categories)
  const locations = flattenTree(references.locations)
  const category = requireNamed(categories, payload.category_name, '资产分类')
  const unit = requireNamed(references.units, payload.unit_name, '计量单位')
  const source = requireNamed(references.sources, payload.source_name, '资产来源')
  const location = requireNamed(locations, payload.location_name, '存放地点')
  const usageCompany = requireNamed(
    flattenTree(references.organizations),
    payload.usage_company_name,
    '使用公司',
  )
  const usageDepartment = payload.usage_department_name
    ? requireNamed(flattenTree(references.organizations), payload.usage_department_name, '使用部门')
    : undefined
  const manager = requireNamed(references.managers, payload.manager_name, '责任管理员')
  const supplier = payload.supplier_name
    ? requireNamed(references.suppliers, payload.supplier_name, '供应商')
    : undefined
  const result = await http.post<unknown, BackendAsset>(`/assets/${assetId}/update`, {
    version: current.version,
    reason: payload.change_reason?.trim() || '修正资产资料',
    asset_name: payload.asset_name,
    category_id: category.id,
    unit_id: unit.id,
    supplier_id: supplier?.id ?? null,
    original_amount: payload.purchase_amount.toFixed(2),
    zero_amount_reason: payload.zero_amount_reason ?? null,
    purchase_date: payload.purchase_date,
    manager_id: manager.id,
    source_id: source.id,
    location_id: location.id,
    usage_company_id: usageCompany.id,
    usage_department_id: usageDepartment?.id ?? null,
    specification_model: payload.model ?? null,
    serial_number: payload.serial_number ?? null,
    rfid_tag: payload.rfid_tag ?? null,
    remark: payload.remark ?? null,
  })
  return mapBackendAsset(result)
}

export interface CsvAssetImportRow {
  organization_name: string
  usage_company_name: string
  usage_department_name?: string
  asset_name: string
  category_name: string
  unit_name: string
  original_amount: number
  zero_amount_reason?: string
  purchase_date: string
  supplier_name?: string
  manager_name: string
  source_name: string
  location_name: string
  specification_model?: string
  serial_number?: string
  rfid_tag?: string
  remark?: string
}

export function createAssetsBatch(
  rows: CsvAssetImportRow[],
  references: AssetReferenceData,
): Promise<StockInSubmitResult> {
  if (!rows.length) throw new Error('导入文件没有可提交的数据')
  if (rows.length > 100) throw new Error('单次导入最多 100 条资产')

  const organizations = flattenTree(references.organizations)
  const categories = flattenTree(references.categories)
  const locations = flattenTree(references.locations)
  const organization = requireNamed(organizations, rows[0].organization_name, '所属公司')
  const usageCompany = requireNamed(organizations, rows[0].usage_company_name, '使用公司')
  if (rows.some((row) => row.organization_name.trim() !== organization.name)) {
    throw new Error('同一个导入文件只能包含一个所属公司')
  }

  return http.post<unknown, StockInSubmitResult>('/stock-in-requests', {
    organization_id: organization.id,
    remark: `CSV 批量导入，共 ${rows.length} 条`,
    idempotency_key: crypto.randomUUID(),
    items: rows.map((row) => {
      const category = requireNamed(categories, row.category_name, '资产分类')
      const unit = requireNamed(references.units, row.unit_name, '计量单位')
      const source = requireNamed(references.sources, row.source_name, '资产来源')
      const location = requireNamed(locations, row.location_name, '存放地点')
      const manager = requireNamed(references.managers, row.manager_name, '责任管理员')
      const supplier = row.supplier_name
        ? requireNamed(references.suppliers, row.supplier_name, '供应商')
        : undefined
      return {
        asset_name: row.asset_name,
        category_id: category.id,
        unit_id: unit.id,
        original_amount: row.original_amount.toFixed(2),
        zero_amount_reason: row.zero_amount_reason || undefined,
        purchase_date: row.purchase_date,
        supplier_id: supplier?.id,
        manager_id: manager.id,
        source_id: source.id,
        location_id: location.id,
        usage_company_id: usageCompany.id,
        usage_department_id: row.usage_department_name
          ? requireNamed(organizations, row.usage_department_name, '使用部门').id
          : null,
        specification_model: row.specification_model || undefined,
        serial_number: row.serial_number || undefined,
        rfid_tag: row.rfid_tag || undefined,
        remark: row.remark || undefined,
        custom_attributes: {},
      }
    }),
  })
}

export const scanLookup = (params: { asset_code?: string; rfid_tag?: string }) =>
  http.get<unknown, AssetSummary>('/assets/scan-lookup', { params })

export const lookupUsageCandidate = (params: { asset_code?: string; rfid_tag?: string }) =>
  http.get<unknown, AssetUsageCandidate>('/assets/usage-candidate', { params })

export const lookupScanIntent = (params: { asset_code?: string; rfid_tag?: string }) =>
  http.get<unknown, AssetScanIntent>('/assets/scan-intent', { params })
