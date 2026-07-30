export interface BackendAsset {
  id: number
  asset_code: string
  asset_name: string
  status: 'IDLE' | 'IN_USE' | 'REPAIRING' | 'SCRAPPED'
  version: number
  company_name?: string | null
  category_name?: string | null
  unit_name?: string | null
  supplier_name?: string | null
  source_name?: string | null
  location_name?: string | null
  manager_name?: string | null
  user_name?: string | null
  department_name?: string | null
  purchase_date: string
  purchase_amount?: number
  original_amount?: string
  information_complete?: boolean
  data_completeness: 'COMPLETE' | 'INCOMPLETE'
  model?: string | null
  specification_model?: string | null
  serial_number?: string | null
  receipt_number?: string | null
  receipt_no?: string | null
  zero_amount_reason?: string | null
  remark?: string | null
  created_at: string
  updated_at: string
}

const fallbackName = (value: string | null | undefined, label: string) => value || `未配置${label}`

export function mapBackendAsset(asset: BackendAsset) {
  return {
    id: asset.id,
    asset_code: asset.asset_code,
    asset_name: asset.asset_name,
    status: asset.status,
    company_name: fallbackName(asset.company_name, '所属公司'),
    category_name: fallbackName(asset.category_name, '资产分类'),
    unit_name: fallbackName(asset.unit_name, '计量单位'),
    supplier_name: asset.supplier_name || undefined,
    source_name: fallbackName(asset.source_name, '资产来源'),
    location_name: fallbackName(asset.location_name, '存放地点'),
    manager_name: asset.manager_name || undefined,
    user_name: asset.user_name || undefined,
    department_name: asset.department_name || undefined,
    purchase_date: asset.purchase_date,
    purchase_amount: asset.purchase_amount ?? Number(asset.original_amount ?? 0),
    information_complete: asset.information_complete ?? asset.data_completeness === 'COMPLETE',
    model: asset.model || asset.specification_model || undefined,
    serial_number: asset.serial_number || undefined,
    receipt_number: asset.receipt_number || asset.receipt_no || undefined,
    zero_amount_reason: asset.zero_amount_reason || undefined,
    remark: asset.remark || undefined,
    created_at: asset.created_at,
    updated_at: asset.updated_at,
  }
}
