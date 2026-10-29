import { canViewAmount, normalizeAssetPayload } from '../assetModel.ts'
import type { AssetDetail, AssetFormValues, AssetPayload } from '../types.ts'

export interface ProtectedFinancialSnapshot {
  purchase_amount: number
  zero_amount_reason?: string
}

export const assetFormDefaultValues: Partial<AssetFormValues> = {
  asset_name: '',
  company_name: '',
  usage_company_name: '',
  usage_department_name: '',
  holder_user_name: '',
  category_name: '',
  source_name: '',
  unit_name: '',
  supplier_name: '',
  purchase_date: '',
  location_name: '',
  zero_amount_reason: '',
  model: '',
  serial_number: '',
  manager_name: '',
  rfid_tag: '',
  change_reason: '',
  remark: '',
}

export function toAssetFormValues(asset: AssetDetail): AssetFormValues {
  return {
    asset_name: asset.asset_name,
    company_name: asset.company_name,
    usage_company_name: asset.usage_company_name ?? '',
    usage_department_name: asset.usage_department_name ?? '',
    holder_user_name: asset.user_name ?? '',
    category_name: asset.category_name,
    source_name: asset.source_name,
    unit_name: asset.unit_name,
    supplier_name: asset.supplier_name,
    purchase_date: asset.purchase_date,
    location_name: asset.location_name,
    purchase_amount: asset.purchase_amount,
    zero_amount_reason: asset.zero_amount_reason ?? '',
    model: asset.model ?? '',
    serial_number: asset.serial_number ?? '',
    manager_name: asset.manager_name ?? '',
    rfid_tag: asset.rfid_tag ?? '',
    change_reason: '',
    remark: asset.remark ?? '',
  }
}

export function buildAssetFormPayload(
  values: AssetFormValues,
  protectedFinancials?: ProtectedFinancialSnapshot,
): AssetPayload {
  const payload = normalizeAssetPayload(values)
  if (protectedFinancials) {
    return {
      ...payload,
      purchase_amount: protectedFinancials.purchase_amount,
      zero_amount_reason: protectedFinancials.zero_amount_reason,
    }
  }

  return {
    ...payload,
    zero_amount_reason: payload.purchase_amount === 0 ? payload.zero_amount_reason : undefined,
  }
}

export function canShowAssetAmount(
  mode: 'create' | 'edit',
  permissions: string[] | undefined,
): boolean {
  return mode === 'create' || canViewAmount(permissions)
}

export function shouldRetryAssetFormQuery(failureCount: number, error: unknown): boolean {
  if (error instanceof Error && error.message === 'ASSET_NOT_FOUND') return false
  return failureCount < 1
}

export function getAssetDetailQueryKey(assetId: number) {
  return ['assets', 'detail', assetId] as const
}

export function getAssetListQueryKey() {
  return ['assets', 'list'] as const
}
