import type { AssetPayload, AssetStatus, AssetTone } from './types.ts'

export type AssetStatusLabelKey =
  | 'assets.status.idle'
  | 'assets.status.pendingReceipt'
  | 'assets.status.inUse'
  | 'assets.status.repairing'
  | 'assets.status.scrapped'

export interface AssetStatusMeta {
  readonly labelKey: AssetStatusLabelKey
  readonly tone: AssetTone
  readonly order: number
}

const assetStatusMeta = Object.freeze({
  IDLE: Object.freeze({ labelKey: 'assets.status.idle', tone: 'brand', order: 1 }),
  PENDING_RECEIPT: Object.freeze({
    labelKey: 'assets.status.pendingReceipt',
    tone: 'warning',
    order: 2,
  }),
  IN_USE: Object.freeze({ labelKey: 'assets.status.inUse', tone: 'success', order: 3 }),
  REPAIRING: Object.freeze({
    labelKey: 'assets.status.repairing',
    tone: 'warning',
    order: 4,
  }),
  SCRAPPED: Object.freeze({ labelKey: 'assets.status.scrapped', tone: 'slate', order: 5 }),
} satisfies Record<AssetStatus, AssetStatusMeta>)

const orderedAssetStatuses: readonly AssetStatus[] = Object.freeze(
  (Object.keys(assetStatusMeta) as AssetStatus[]).sort(
    (left, right) => assetStatusMeta[left].order - assetStatusMeta[right].order,
  ),
)

const trimOptional = (value: string | undefined): string | undefined => {
  const trimmed = value?.trim()
  return trimmed ? trimmed : undefined
}

export function parseAssetCodes(value: string): string[] {
  const codes = value.split(/[\s,，]+/)
  const uniqueCodes: string[] = []
  const codeIndex: Record<string, true> = {}

  codes.forEach((code) => {
    const trimmed = code.trim()
    const indexKey = `asset-code:${trimmed}`
    if (trimmed && codeIndex[indexKey] !== true) {
      codeIndex[indexKey] = true
      uniqueCodes.push(trimmed)
    }
  })

  return uniqueCodes
}

export function getAssetStatusMeta(status: AssetStatus): AssetStatusMeta {
  return assetStatusMeta[status]
}

export function getOrderedAssetStatuses(): readonly AssetStatus[] {
  return orderedAssetStatuses
}

export function canViewAmount(permissions: string[] | undefined): boolean {
  return permissions !== undefined && permissions.indexOf('asset:amount:view') >= 0
}

export function canViewAssets(permissions: string[] | undefined): boolean {
  return permissions !== undefined && permissions.indexOf('asset:view') >= 0
}

export function canCreateAsset(permissions: string[] | undefined): boolean {
  return (
    permissions !== undefined &&
    (permissions.indexOf('asset:create') >= 0 || permissions.indexOf('stock-in:create') >= 0)
  )
}

export function normalizeAssetPayload(values: AssetPayload): AssetPayload {
  return {
    asset_name: values.asset_name.trim(),
    company_name: values.company_name.trim(),
    usage_company_name: values.usage_company_name.trim(),
    usage_department_name: trimOptional(values.usage_department_name),
    holder_user_name: trimOptional(values.holder_user_name),
    category_name: values.category_name.trim(),
    source_name: values.source_name.trim(),
    unit_name: values.unit_name.trim(),
    supplier_name: trimOptional(values.supplier_name),
    purchase_date: values.purchase_date.trim(),
    location_name: values.location_name.trim(),
    purchase_amount: values.purchase_amount,
    zero_amount_reason: trimOptional(values.zero_amount_reason),
    model: trimOptional(values.model),
    serial_number: trimOptional(values.serial_number),
    manager_name: values.manager_name.trim(),
    rfid_tag: trimOptional(values.rfid_tag),
    change_reason: trimOptional(values.change_reason),
    remark: trimOptional(values.remark),
  }
}
