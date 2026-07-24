import type { PageResult } from '../types/index.ts'
import { normalizeAssetPayload } from '../features/assets/assetModel.ts'
import { demoAssets } from '../features/assets/assetData.ts'
import type {
  AssetDetail,
  AssetListQuery,
  AssetPayload,
  AssetSummary,
} from '../features/assets/types.ts'

let assetStore: AssetDetail[] = demoAssets.map((asset) => ({ ...asset }))
let nextAssetId = assetStore.reduce((highestId, asset) => Math.max(highestId, asset.id), 0) + 1

const summaryFields = (asset: AssetDetail): AssetSummary => ({
  id: asset.id,
  asset_code: asset.asset_code,
  asset_name: asset.asset_name,
  category_name: asset.category_name,
  status: asset.status,
  model: asset.model,
  serial_number: asset.serial_number,
  receipt_number: asset.receipt_number,
  user_name: asset.user_name,
  department_name: asset.department_name,
  location_name: asset.location_name,
  manager_name: asset.manager_name,
  company_name: asset.company_name,
  supplier_name: asset.supplier_name,
  source_name: asset.source_name,
  unit_name: asset.unit_name,
  purchase_date: asset.purchase_date,
  purchase_amount: asset.purchase_amount,
  information_complete: asset.information_complete,
})

const cloneDetail = (asset: AssetDetail): AssetDetail => ({ ...asset })

const includesText = (value: string | undefined, expected: string): boolean =>
  value !== undefined && value.toLocaleLowerCase().indexOf(expected) >= 0

const isFiniteInteger = (value: number): boolean =>
  value === value && value !== Infinity && value !== -Infinity && Math.floor(value) === value

const normalizePage = (page: number): number => (isFiniteInteger(page) && page > 0 ? page : 1)

const normalizeSize = (size: number): 20 | 50 | 100 => {
  if (size === 20 || size === 50 || size === 100) return size
  return 50
}

const padNumber = (value: number, minimumLength: number): string => {
  let result = String(value)
  while (result.length < minimumLength) result = `0${result}`
  return result
}

function createAssetCode(now: Date): string {
  const prefix = `PC-${now.getFullYear()}-`
  let highestSequence = 0

  assetStore.forEach((asset) => {
    if (asset.asset_code.indexOf(prefix) !== 0) return

    const sequence = Number(asset.asset_code.slice(prefix.length))
    if (isFiniteInteger(sequence) && sequence > highestSequence) highestSequence = sequence
  })

  return `${prefix}${padNumber(highestSequence + 1, 3)}`
}

function matchesKeyword(asset: AssetDetail, keyword: string | undefined): boolean {
  const expected = keyword?.trim().toLocaleLowerCase()
  if (!expected) return true

  return [
    asset.asset_code,
    asset.asset_name,
    asset.serial_number,
    asset.user_name,
    asset.receipt_number,
  ].some((value) => includesText(value, expected))
}

function matchesExactFilter(value: string | undefined, expected: string | undefined): boolean {
  return !expected || value === expected
}

function buildAssetCodeIndex(
  assetCodes: readonly string[] | undefined,
): Record<string, true> | null {
  if (!assetCodes?.length) return null

  const index: Record<string, true> = {}
  assetCodes.forEach((assetCode) => {
    index[`asset-code:${assetCode}`] = true
  })
  return index
}

function matchesQuery(
  asset: AssetDetail,
  query: AssetListQuery,
  assetCodeIndex: Record<string, true> | null,
): boolean {
  if (!matchesKeyword(asset, query.keyword)) return false
  if (assetCodeIndex && assetCodeIndex[`asset-code:${asset.asset_code}`] !== true) return false
  if (!matchesExactFilter(asset.company_name, query.company_name)) return false
  if (!matchesExactFilter(asset.category_name, query.category_name)) return false
  if (query.status && asset.status !== query.status) return false
  if (!matchesExactFilter(asset.department_name, query.department_name)) return false
  if (!matchesExactFilter(asset.location_name, query.location_name)) return false
  if (
    query.information_complete !== undefined &&
    asset.information_complete !== query.information_complete
  ) {
    return false
  }
  if (!matchesExactFilter(asset.user_name, query.user_name)) return false
  if (!matchesExactFilter(asset.manager_name, query.manager_name)) return false
  if (!matchesExactFilter(asset.supplier_name, query.supplier_name)) return false
  if (!matchesExactFilter(asset.source_name, query.source_name)) return false
  if (query.purchase_date_from && asset.purchase_date < query.purchase_date_from) return false
  if (query.purchase_date_to && asset.purchase_date > query.purchase_date_to) return false
  return true
}

export function listAssets(query: AssetListQuery): Promise<PageResult<AssetSummary>> {
  const size = normalizeSize(query.size)
  const assetCodeIndex = buildAssetCodeIndex(query.asset_codes)
  const filtered = assetStore.filter((asset) => matchesQuery(asset, query, assetCodeIndex))
  const total = filtered.length
  const lastPage = Math.max(1, Math.ceil(total / size))
  const page = Math.min(normalizePage(query.page), lastPage)
  const start = (page - 1) * size
  const records = filtered.slice(start, start + size).map(summaryFields)

  return Promise.resolve({ records, total, page, size })
}

export function getAsset(assetId: number): Promise<AssetDetail> {
  const asset = assetStore.find((item) => item.id === assetId)
  return asset ? Promise.resolve(cloneDetail(asset)) : Promise.reject(new Error('ASSET_NOT_FOUND'))
}

export function createAsset(payload: AssetPayload): Promise<AssetDetail> {
  const values = normalizeAssetPayload(payload)
  const now = new Date()
  const asset: AssetDetail = {
    ...values,
    id: nextAssetId,
    asset_code: createAssetCode(now),
    status: 'IDLE',
    information_complete: true,
    created_at: now.toISOString(),
    updated_at: now.toISOString(),
  }

  nextAssetId += 1
  assetStore = assetStore.concat(asset)
  return Promise.resolve(cloneDetail(asset))
}

export function updateAsset(assetId: number, payload: AssetPayload): Promise<AssetDetail> {
  const current = assetStore.find((asset) => asset.id === assetId)
  if (!current) return Promise.reject(new Error('ASSET_NOT_FOUND'))

  const updated: AssetDetail = {
    ...current,
    ...normalizeAssetPayload(payload),
    updated_at: new Date().toISOString(),
  }
  assetStore = assetStore.map((asset) => (asset.id === assetId ? updated : asset))
  return Promise.resolve(cloneDetail(updated))
}
