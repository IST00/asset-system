import http from '@/api/http'
import type { OperationRequest } from '@/api/operations'

export type AssetUsageReturnAction =
  | 'PERSONAL_USE'
  | 'PUBLIC_USE'
  | 'PERSONAL_RETURN'
  | 'PUBLIC_RETURN'

export type ReturnCondition = 'NORMAL' | 'DAMAGED'

export interface ReturnInspectionItem {
  asset_id: number
  condition: ReturnCondition
  condition_description?: string
}

export type AssetUsageReturnSubmission =
  | {
      action: 'PERSONAL_USE'
      asset_ids: number[]
      target_user_id: number
      location_id?: number
    }
  | {
      action: 'PUBLIC_USE'
      asset_ids: number[]
      public_object_id: number
      location_id: number
    }
  | {
      action: 'PERSONAL_RETURN'
      asset_ids: number[]
    }
  | {
      action: 'PUBLIC_RETURN'
      asset_ids: number[]
      return_location_id: number
      items: ReturnInspectionItem[]
    }

const idempotencyKey = (): string => crypto.randomUUID()

export const assetUsageReturnApi = {
  submit: (submission: AssetUsageReturnSubmission): Promise<OperationRequest> => {
    const { action, ...payload } = submission
    if (action === 'PERSONAL_USE') {
      return http.post<unknown, OperationRequest>('/asset-usage-requests/personal', {
        ...payload,
        idempotency_key: idempotencyKey(),
      })
    }
    if (action === 'PUBLIC_USE') {
      return http.post<unknown, OperationRequest>('/asset-usage-requests/public', {
        ...payload,
        idempotency_key: idempotencyKey(),
      })
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
  confirmPersonalReturn: (
    operationRequestId: number,
    payload: { return_location_id: number; items: ReturnInspectionItem[] },
  ) =>
    http.post<unknown, OperationRequest>(`/asset-return-requests/${operationRequestId}/confirm`, {
      ...payload,
      idempotency_key: idempotencyKey(),
    }),
}
