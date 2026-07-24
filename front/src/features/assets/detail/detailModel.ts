export type AssetDetailTabKey =
  | 'basic'
  | 'attachments'
  | 'relations'
  | 'history'
  | 'repairs'
  | 'scrap'
  | 'inventory'
  | 'approvals'

export interface AssetDetailTab {
  readonly key: AssetDetailTabKey
  readonly labelKey: `assets.detail.tabs.${AssetDetailTabKey}`
}

export const assetDetailTabs: readonly AssetDetailTab[] = Object.freeze([
  { key: 'basic', labelKey: 'assets.detail.tabs.basic' },
  { key: 'attachments', labelKey: 'assets.detail.tabs.attachments' },
  { key: 'relations', labelKey: 'assets.detail.tabs.relations' },
  { key: 'history', labelKey: 'assets.detail.tabs.history' },
  { key: 'repairs', labelKey: 'assets.detail.tabs.repairs' },
  { key: 'scrap', labelKey: 'assets.detail.tabs.scrap' },
  { key: 'inventory', labelKey: 'assets.detail.tabs.inventory' },
  { key: 'approvals', labelKey: 'assets.detail.tabs.approvals' },
])

export type DetailFieldGroupKey = 'basic' | 'ownership' | 'purchase' | 'management'
export type DetailFieldKey =
  | 'asset_code'
  | 'asset_name'
  | 'category_name'
  | 'status'
  | 'model'
  | 'serial_number'
  | 'receipt_number'
  | 'user_name'
  | 'department_name'
  | 'location_name'
  | 'manager_name'
  | 'company_name'
  | 'supplier_name'
  | 'source_name'
  | 'unit_name'
  | 'purchase_date'
  | 'purchase_amount'
  | 'information_complete'
  | 'zero_amount_reason'
  | 'remark'
  | 'created_at'
  | 'updated_at'

export interface DetailFieldGroup {
  readonly key: DetailFieldGroupKey
  readonly titleKey: `assets.detail.sections.${'identity' | 'usage' | 'purchase' | 'management'}`
  readonly fields: readonly DetailFieldKey[]
}

const basicFields: readonly DetailFieldKey[] = [
  'asset_code',
  'asset_name',
  'category_name',
  'status',
  'model',
  'serial_number',
  'receipt_number',
]

const ownershipFields: readonly DetailFieldKey[] = [
  'company_name',
  'user_name',
  'department_name',
  'location_name',
]

const purchaseFields: readonly DetailFieldKey[] = [
  'supplier_name',
  'source_name',
  'unit_name',
  'purchase_date',
]

const managementFields: readonly DetailFieldKey[] = [
  'manager_name',
  'information_complete',
  'remark',
  'created_at',
  'updated_at',
]

export function getDetailFieldGroups(canViewPurchaseAmount: boolean): DetailFieldGroup[] {
  const permittedPurchaseFields = canViewPurchaseAmount
    ? purchaseFields.concat('purchase_amount', 'zero_amount_reason')
    : purchaseFields

  return [
    { key: 'basic', titleKey: 'assets.detail.sections.identity', fields: basicFields },
    { key: 'ownership', titleKey: 'assets.detail.sections.usage', fields: ownershipFields },
    {
      key: 'purchase',
      titleKey: 'assets.detail.sections.purchase',
      fields: permittedPurchaseFields,
    },
    {
      key: 'management',
      titleKey: 'assets.detail.sections.management',
      fields: managementFields,
    },
  ]
}
