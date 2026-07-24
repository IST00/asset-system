export type AssetStatus = 'IDLE' | 'IN_USE' | 'REPAIRING' | 'SCRAPPED'

export type AssetTone = 'brand' | 'success' | 'warning' | 'danger' | 'slate'

export interface AssetSummary {
  id: number
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
}

export interface AssetDetail extends AssetSummary {
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
  page: number
  size: 20 | 50 | 100
}

export interface AssetFormValues {
  asset_name: string
  company_name: string
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
  remark?: string
}

export type AssetPayload = AssetFormValues
