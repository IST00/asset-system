import http from '@/api/http'
import type { OperationRequest } from '@/api/operations'
import { localFeishuActionPath } from '@/api/assetUsageReturnPaths'

export type AssetUsageReturnAction =
  | 'PERSONAL_USE'
  | 'PERSONAL_BORROW'
  | 'PUBLIC_USE'
  | 'PUBLIC_BORROW'
  | 'PERSONAL_RETURN'
  | 'PUBLIC_RETURN'

export type ReturnCondition = 'NORMAL' | 'DAMAGED'

export interface ReturnInspectionItem {
  asset_id: number
  condition: ReturnCondition
  condition_description?: string
}

export interface SelfServiceReferenceOption {
  id: number
  code: string
  name: string
  available_quantity?: number
}

export interface SelfServiceReferences {
  categories: SelfServiceReferenceOption[]
  locations: SelfServiceReferenceOption[]
}

export interface MyAsset {
  id: number
  asset_code: string
  asset_name: string
  status: 'IN_USE'
  location_id?: number | null
  location_name?: string | null
  usage_mode: 'USE' | 'BORROW'
  expected_return_at?: string | null
}

export interface IssueCandidateAsset {
  id: number
  asset_code: string
  asset_name: string
  status: 'IDLE'
  organization_id: number
  organization_name?: string | null
  location_name?: string | null
  specification_model?: string | null
  serial_number?: string | null
}

export interface BorrowExtensionRequest {
  id: number
  operation_request_id: number
  request_no?: string | null
  applicant_id: number
  original_expected_return_at: string
  requested_expected_return_at: string
  reason: string
  status: 'PENDING' | 'APPROVED' | 'REJECTED'
  reviewed_by: number | null
  reviewed_at: string | null
  review_opinion: string | null
  version: number
  created_at: string
  updated_at: string
}

export interface IssueCandidates {
  requested_quantity: number
  requested_category?: { id: number; code: string; name: string } | null
  items: IssueCandidateAsset[]
}

export type AssetUsageReturnSubmission =
  | {
      action: 'PERSONAL_USE'
      asset_ids?: number[]
      category_id?: number
      requested_quantity?: number
      target_user_id?: number
      location_id?: number
      reason?: string
    }
  | {
      action: 'PERSONAL_BORROW'
      asset_ids?: number[]
      category_id?: number
      requested_quantity?: number
      target_user_id?: number
      location_id?: number
      expected_return_at: string
      reason?: string
    }
  | {
      action: 'PERSONAL_RETURN'
      asset_ids: number[]
    }
  | {
      action: 'PUBLIC_USE'
      asset_ids: number[]
      public_object_id: number
      location_id: number
    }
  | {
      action: 'PUBLIC_BORROW'
      asset_ids: number[]
      public_object_id: number
      location_id: number
      expected_return_at: string
    }
  | {
      action: 'PUBLIC_RETURN'
      asset_ids: number[]
      return_company_id: number
      return_usage_company_id: number
      return_region_id: number
      return_location_id: number
      items: ReturnInspectionItem[]
    }

const idempotencyKey = (): string => crypto.randomUUID()

export const assetUsageReturnApi = {
  selfServiceReferences: (): Promise<SelfServiceReferences> =>
    http.get<unknown, SelfServiceReferences>('/asset-usage-requests/self-service-references'),
  myAssets: (): Promise<MyAsset[]> =>
    http.get<unknown, MyAsset[]>('/asset-usage-requests/my-assets'),
  submit: (submission: AssetUsageReturnSubmission): Promise<OperationRequest> => {
    const { action, ...payload } = submission
    if (action === 'PERSONAL_USE' || action === 'PERSONAL_BORROW') {
      const selfService = !('target_user_id' in payload) || payload.target_user_id === undefined
      return http.post<unknown, OperationRequest>(
        selfService
          ? action === 'PERSONAL_BORROW'
            ? '/asset-usage-requests/personal-borrow-self'
            : '/asset-usage-requests/personal-self'
          : action === 'PERSONAL_BORROW'
            ? '/asset-usage-requests/personal-borrow'
            : '/asset-usage-requests/personal',
        {
          ...payload,
          idempotency_key: idempotencyKey(),
        },
      )
    }
    if (action === 'PUBLIC_USE' || action === 'PUBLIC_BORROW') {
      return http.post<unknown, OperationRequest>(
        action === 'PUBLIC_BORROW'
          ? '/asset-usage-requests/public-borrow'
          : '/asset-usage-requests/public',
        {
          ...payload,
          idempotency_key: idempotencyKey(),
        },
      )
    }
    if (action === 'PERSONAL_RETURN') {
      return http.post<unknown, OperationRequest>('/asset-return-requests/personal', {
        ...payload,
        idempotency_key: idempotencyKey(),
      })
    }
    return http.post<unknown, OperationRequest>('/asset-return-requests/public', {
      ...payload,
      idempotency_key: idempotencyKey(),
    })
  },
  handoverPersonalReturn: (
    operationRequestId: number,
    remark?: string,
  ): Promise<OperationRequest> =>
    http.post<unknown, OperationRequest>(`/asset-return-requests/${operationRequestId}/handover`, {
      remark,
    }),
  requestBorrowReturn: (operationRequestId: number, reason: string): Promise<OperationRequest> =>
    http.post<unknown, OperationRequest>(
      `/asset-usage-requests/${operationRequestId}/request-return`,
      { reason },
    ),
  confirmPersonalReturn: (
    operationRequestId: number,
    payload: {
      return_company_id: number
      return_usage_company_id: number
      return_region_id: number
      return_location_id: number
      items: ReturnInspectionItem[]
    },
  ) =>
    http.post<unknown, OperationRequest>(`/asset-return-requests/${operationRequestId}/confirm`, {
      ...payload,
      idempotency_key: idempotencyKey(),
    }),
  pendingBorrowExtensions: (): Promise<BorrowExtensionRequest[]> =>
    http.get<unknown, BorrowExtensionRequest[]>('/asset-usage-requests/borrow-extensions/pending'),
  listBorrowExtensions: (operationRequestId: number): Promise<BorrowExtensionRequest[]> =>
    http.get<unknown, BorrowExtensionRequest[]>(
      `/asset-usage-requests/${operationRequestId}/extensions`,
    ),
  createBorrowExtension: (
    operationRequestId: number,
    payload: { requested_expected_return_at: string; reason: string },
  ): Promise<BorrowExtensionRequest> =>
    http.post<unknown, BorrowExtensionRequest>(
      `/asset-usage-requests/${operationRequestId}/extensions`,
      payload,
    ),
  approveBorrowExtension: (extensionId: number, opinion?: string) =>
    http.post<unknown, BorrowExtensionRequest>(
      `/asset-usage-requests/borrow-extensions/${extensionId}/approve`,
      { opinion },
    ),
  rejectBorrowExtension: (extensionId: number, opinion: string) =>
    http.post<unknown, BorrowExtensionRequest>(
      `/asset-usage-requests/borrow-extensions/${extensionId}/reject`,
      { opinion },
    ),
  issueCandidates: (operationRequestId: number): Promise<IssueCandidates> =>
    http.get<unknown, IssueCandidates>(
      `/asset-usage-requests/${operationRequestId}/issue-candidates`,
    ),
  issue: (
    operationRequestId: number,
    payload: {
      asset_ids: number[]
      region_id: number
      location_id: number
      remark?: string
    },
  ): Promise<OperationRequest> =>
    http.post<unknown, OperationRequest>(`/asset-usage-requests/${operationRequestId}/issue`, {
      ...payload,
    }),
  sign: (operationRequestId: number, remark?: string): Promise<OperationRequest> =>
    http.post<unknown, OperationRequest>(`/asset-usage-requests/${operationRequestId}/sign`, {
      remark,
    }),
  refuseSign: (operationRequestId: number, remark: string): Promise<OperationRequest> =>
    http.post<unknown, OperationRequest>(
      `/asset-usage-requests/${operationRequestId}/refuse-sign`,
      { remark },
    ),
  mockFeishuAction: (
    operationRequestId: number,
    operationType: string,
    action: 'APPROVE' | 'REJECT',
    reason?: string,
  ): Promise<OperationRequest> =>
    http.post<unknown, OperationRequest>(localFeishuActionPath(operationRequestId, operationType), {
      action,
      external_event_id: crypto.randomUUID(),
      reason,
    }),
}
