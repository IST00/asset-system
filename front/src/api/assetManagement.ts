import http from '@/api/http'
import { mapBackendAsset, type BackendAsset } from '@/api/assetMapper'
import type { AssetDetail } from '@/features/assets/types'

export interface AssetTarget {
  asset_id: number
  version: number
}

export interface AssetCommandResult {
  command_no: string
  updated_count: number
  items: AssetDetail[]
}

interface BackendAssetCommandResult {
  command_no?: string
  request_no?: string
  batch_no?: string
  updated_count: number
  items: BackendAsset[]
}

export interface AssetRelations {
  main: AssetDetail
  attachments: AssetDetail[]
}

export interface PublicUsageObject {
  id: number
  code: string
  name: string
  status: 'ENABLED' | 'DISABLED'
  usage_count: number
  created_at: string
  updated_at: string
}

const mapCommand = (result: BackendAssetCommandResult): AssetCommandResult => ({
  command_no: result.command_no ?? result.request_no ?? result.batch_no ?? 'UNKNOWN',
  updated_count: result.updated_count,
  items: result.items.map(mapBackendAsset),
})

export const assetManagementApi = {
  batchUpdate: async (payload: {
    items: AssetTarget[]
    changes: Record<string, string | number | null>
    reason: string
  }) =>
    mapCommand(
      await http.post<unknown, BackendAssetCommandResult>('/assets/batch-update', payload),
    ),
  relations: async (assetId: number) => {
    const result = await http.get<unknown, { main: BackendAsset; attachments: BackendAsset[] }>(
      `/assets/${assetId}/relations`,
    )
    return {
      main: mapBackendAsset(result.main),
      attachments: result.attachments.map(mapBackendAsset),
    }
  },
  attach: async (assetId: number, childIds: number[], reason: string) => {
    const result = await http.post<unknown, { main: BackendAsset; attachments: BackendAsset[] }>(
      `/assets/${assetId}/relations/attach`,
      { child_ids: childIds, reason },
    )
    return {
      main: mapBackendAsset(result.main),
      attachments: result.attachments.map(mapBackendAsset),
    }
  },
  detach: async (assetId: number, childIds: number[], reason: string) => {
    const result = await http.post<unknown, { main: BackendAsset; attachments: BackendAsset[] }>(
      `/assets/${assetId}/relations/detach`,
      { child_ids: childIds, reason },
    )
    return {
      main: mapBackendAsset(result.main),
      attachments: result.attachments.map(mapBackendAsset),
    }
  },
  publicObjects: (includeDisabled = false) =>
    http.get<unknown, PublicUsageObject[]>('/public-usage-objects', {
      params: { include_disabled: includeDisabled },
    }),
  createPublicObject: (name: string) =>
    http.post<unknown, PublicUsageObject>('/public-usage-objects', { name }),
  updatePublicObject: (id: number, changes: { name?: string; status?: 'ENABLED' | 'DISABLED' }) =>
    http.post<unknown, PublicUsageObject>(`/public-usage-objects/${id}/update`, changes),
  transfer: async (payload: {
    items: AssetTarget[]
    location_id?: number
    manager_id?: number
    holder_user_id?: number | null
    public_object_id?: number | null
    reason: string
  }) => mapCommand(await http.post('/asset-actions/transfer', payload)),
  repairStart: async (payload: {
    items: AssetTarget[]
    vendor?: string
    estimated_cost?: string
    reason: string
  }) => mapCommand(await http.post('/asset-actions/repair/start', payload)),
  repairComplete: async (payload: { items: AssetTarget[]; actual_cost?: string; result: string }) =>
    mapCommand(await http.post('/asset-actions/repair/complete', payload)),
  scrap: async (payload: {
    items: AssetTarget[]
    scrap_date: string
    scrap_amount?: string
    child_action: 'BLOCK' | 'DETACH' | 'SCRAP'
    reason: string
  }) => mapCommand(await http.post('/asset-actions/scrap', payload)),
}
