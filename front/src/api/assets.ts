import http from '@/api/http'
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
  before_data: Record<string, unknown> | null
  after_data: Record<string, unknown> | null
  remark?: string | null
  created_at: string
}

import { mapBackendAsset, type BackendAsset } from '@/api/assetMapper'

const toSummary = (asset: AssetDetail): AssetSummary => asset

export async function listAssets(query: AssetListQuery): Promise<PageResult<AssetSummary>> {
  const params: Record<string, string | number> = {
    page: Math.max(0, query.page - 1),
    size: query.size,
  }
  const keyword = query.keyword?.trim()
  if (keyword) params.asset_name = keyword
  if (query.asset_codes?.length === 1) params.asset_code = query.asset_codes[0]
  if (query.information_complete !== undefined) {
    params.data_completeness = query.information_complete ? 'COMPLETE' : 'INCOMPLETE'
  }

  const result = await http.get<unknown, BackendPage<BackendAsset>>('/assets', { params })
  const records = result.items.map(mapBackendAsset).filter((asset) => {
    if (query.status && asset.status !== query.status) return false
    if (query.company_name && asset.company_name !== query.company_name) return false
    if (query.category_name && asset.category_name !== query.category_name) return false
    if (query.department_name && asset.department_name !== query.department_name) return false
    if (query.location_name && asset.location_name !== query.location_name) return false
    if (query.user_name && asset.user_name !== query.user_name) return false
    if (query.manager_name && asset.manager_name !== query.manager_name) return false
    if (query.supplier_name && asset.supplier_name !== query.supplier_name) return false
    if (query.source_name && asset.source_name !== query.source_name) return false
    if (query.purchase_date_from && asset.purchase_date < query.purchase_date_from) return false
    if (query.purchase_date_to && asset.purchase_date > query.purchase_date_to) return false
    return true
  })

  return {
    records: records.map(toSummary),
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

export function createAsset(_payload: AssetPayload): Promise<AssetDetail> {
  return Promise.reject(new Error('新增资产需通过入库申请完成，请前往业务流程创建入库申请'))
}

export function updateAsset(_assetId: number, _payload: AssetPayload): Promise<AssetDetail> {
  return Promise.reject(new Error('正式资产不支持直接修改，请通过资料补录或业务流程发起变更'))
}
