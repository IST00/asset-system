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

export interface AssetFinancialSummary {
  asset_id: number
  asset_code: string
  asset_name: string
  status: string
  method: 'STRAIGHT_LINE'
  method_name: string
  currency: 'CNY'
  original_amount: string
  residual_value: string
  depreciable_amount: string
  monthly_depreciation: string
  accumulated_depreciation: string
  net_book_value: string
  zero_amount_reason?: string | null
  purchase_date: string
  as_of: string
  service_life_months: number
  elapsed_months: number
  remaining_months: number
  expected_expiry_date: string
  is_fully_depreciated: boolean
}

export interface AssetScrapRecord {
  id: number
  asset_id: number
  scrap_no: string
  scrap_date: string
  scrap_amount?: string | null
  reason: string
  disposition?: string | null
  disposition_remark?: string | null
  disposal_date?: string | null
  confirmed_by: number
  confirmed_at: string
  created_at: string
  updated_at: string
}

export interface AssetRepairRecord {
  id: number
  asset_id: number
  repair_no: string
  before_status: string
  fault_description: string
  repair_supplier_id?: number | null
  repair_supplier_name?: string | null
  repair_cost?: string | null
  sent_at: string
  completed_at?: string | null
  repair_result?: string | null
  confirmed_by?: number | null
  confirmed_at?: string | null
  created_at: string
  updated_at: string
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

export interface TransferHandover {
  id: number
  handover_no: string
  initiated_by: number
  initiated_by_user?: { id: number; name: string } | null
  outgoing_user_id: number | null
  outgoing_user?: { id: number; name: string } | null
  receiver_user_id: number | null
  receiver_user?: { id: number; name: string } | null
  organization_id: number | null
  location_id: number | null
  manager_id: number | null
  manager_user?: { id: number; name: string } | null
  reason: string
  handover_token?: string | null
  items: Array<{ asset_id: number; asset_code: string; asset_name: string; version: number }>
  status: 'PENDING_OUTGOING' | 'PENDING_RECEIPT' | 'COMPLETED' | 'REJECTED'
  outgoing_confirmed_at: string | null
  received_confirmed_at: string | null
  reject_reason: string | null
  created_at: string
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
  financialSummary: (assetId: number, asOf?: string) =>
    http.get<unknown, AssetFinancialSummary>(`/assets/${assetId}/financial-summary`, {
      params: asOf ? { as_of: asOf } : undefined,
    }),
  repairRecords: (assetId: number) =>
    http.get<unknown, AssetRepairRecord[]>(`/assets/${assetId}/repair-records`),
  scrapRecords: (assetId: number) =>
    http.get<unknown, AssetScrapRecord[]>(`/assets/${assetId}/scrap-records`),
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
  transferHandover: async (payload: {
    items: AssetTarget[]
    receiver_user_id?: number | null
    outgoing_user_id?: number | null
    organization_id?: number
    location_id?: number
    manager_id?: number
    reason?: string
  }) =>
    http.post<
      unknown,
      {
        id: number
        handover_no: string
        status: string
        updated_count?: number
        command_no?: string
        handover_token?: string | null
        items: TransferHandover['items']
      }
    >('/asset-actions/transfer-handover', payload),
  transferHandoverByToken: (handoverToken: string) =>
    http.get<unknown, TransferHandover>(
      `/asset-actions/transfer-handovers/by-token/${encodeURIComponent(handoverToken)}`,
    ),
  claimTransferHandoverByToken: (payload: { handover_token: string; remark?: string }) =>
    http.post<unknown, TransferHandover>(
      '/asset-actions/transfer-handovers/claim-by-token',
      payload,
    ),
  pendingTransferHandovers: () =>
    http.get<unknown, TransferHandover[]>('/asset-actions/transfer-handovers/pending'),
  receivedTransferHandovers: () =>
    http.get<unknown, TransferHandover[]>('/asset-actions/transfer-handovers/received'),
  confirmTransferOutgoing: (id: number, remark?: string) =>
    http.post<unknown, TransferHandover>(
      `/asset-actions/transfer-handovers/${id}/confirm-outgoing`,
      { remark },
    ),
  confirmTransferReceipt: (id: number, remark?: string) =>
    http.post<unknown, TransferHandover>(
      `/asset-actions/transfer-handovers/${id}/confirm-receipt`,
      { remark },
    ),
  rejectTransferHandover: (id: number, reason: string) =>
    http.post<unknown, TransferHandover>(`/asset-actions/transfer-handovers/${id}/reject`, {
      reason,
    }),
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
    items: Array<
      AssetTarget & {
        scrap_amount: string
        disposition?: string | null
        disposition_remark?: string | null
        disposal_date: string
      }
    >
    child_action: 'BLOCK' | 'DETACH' | 'SCRAP'
    reason: string
  }) => mapCommand(await http.post('/asset-actions/scrap', payload)),
}
