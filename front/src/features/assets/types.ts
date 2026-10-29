export type AssetStatus = 'IDLE' | 'PENDING_RECEIPT' | 'IN_USE' | 'REPAIRING' | 'SCRAPPED'

export type AssetTone = 'brand' | 'success' | 'warning' | 'danger' | 'slate'

export interface AssetSummary {
  id: number
  version: number
  asset_code: string
  asset_name: string
  category_name: string
  status: AssetStatus
  model?: string
  serial_number?: string
  receipt_number?: string
  user_name?: string
  department_name?: string
  location_name: string
  manager_name?: string
  company_name: string
  supplier_name?: string
  source_name: string
  unit_name: string
  purchase_date: string
  purchase_amount: number
  information_complete: boolean
  organization_id?: number
  usage_company_id?: number
  usage_company_name?: string
  usage_department_id?: number
  usage_department_name?: string
  parent_asset_id?: number
  holder_user_id?: number
  public_object_id?: number
  usage_type?: string
}

export interface AssetDetail extends AssetSummary {
  rfid_tag?: string
  category_id?: number
  unit_id?: number
  supplier_id?: number
  manager_id?: number
  source_id?: number
  location_id?: number
  holder_user_id?: number
  usage_department_id?: number
  public_object_id?: number
  zero_amount_reason?: string
  remark?: string
  created_at: string
  updated_at: string
}

export interface AssetListQuery {
  keyword?: string
  asset_codes?: string[]
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
  only_my_assets?: boolean
  page: number
  size: 20 | 50 | 100
}

export interface AssetFormValues {
  asset_name: string
  company_name: string
  usage_company_name: string
  usage_department_name?: string
  holder_user_name?: string
  category_name: string
  source_name: string
  unit_name: string
  supplier_name?: string
  purchase_date: string
  location_name: string
  purchase_amount: number
  zero_amount_reason?: string
  model?: string
  serial_number?: string
  manager_name: string
  rfid_tag?: string
  change_reason?: string
  remark?: string
}

export type AssetPayload = AssetFormValues
