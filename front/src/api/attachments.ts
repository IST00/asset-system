import http from '@/api/http'

export type AssetAttachmentType =
  | 'PHOTO'
  | 'CONTRACT'
  | 'INVOICE'
  | 'ACCEPTANCE'
  | 'REPAIR'
  | 'SCRAP'
  | 'USAGE_SIGN'
  | 'RETURN_HANDOVER'
  | 'RETURN_INSPECTION'
  | 'TRANSFER_RECEIPT'
  | 'OTHER'

export type AssetAttachmentDocumentType =
  | 'ASSET_PHOTO'
  | 'CONTRACT'
  | 'INVOICE'
  | 'ACCEPTANCE'
  | 'REPAIR_PHOTO'
  | 'REPAIR_QUOTE'
  | 'REPAIR_INVOICE'
  | 'SCRAP_CERTIFICATE'
  | 'DISPOSAL_VOUCHER'
  | 'SIGN_PHOTO'
  | 'RETURN_PHOTO'
  | 'INSPECTION_PHOTO'
  | 'TRANSFER_RECEIPT_PHOTO'
  | 'ELECTRONIC_SIGNATURE'
  | 'OTHER'

export interface AssetAttachment {
  id: number
  asset_id: number
  business_type: AssetAttachmentType
  business_id?: number | null
  document_type: AssetAttachmentDocumentType
  original_name: string
  mime_type: string
  size_bytes: number
  sha256: string
  is_cover: boolean
  status: 'ACTIVE' | 'VOIDED'
  uploaded_by: number
  voided_by?: number
  voided_at?: string
  void_reason?: string
  version: number
  created_at: string
  updated_at: string
}

export interface AttachmentListFilters {
  business_type?: AssetAttachmentType
  business_id?: number
}

export interface AttachmentUploadPayload {
  businessType: AssetAttachmentType
  businessId?: number | null
  documentType: AssetAttachmentDocumentType
  file: File
}

export const attachmentApi = {
  list(assetId: number, filters?: AttachmentListFilters): Promise<AssetAttachment[]> {
    return http.get(`/assets/${assetId}/attachments`, { params: filters })
  },

  upload(assetId: number, payload: AttachmentUploadPayload) {
    const data = new FormData()
    data.append('business_type', payload.businessType)
    data.append('document_type', payload.documentType)
    if (payload.businessId != null) data.append('business_id', String(payload.businessId))
    data.append('file', payload.file)
    return http.post<unknown, AssetAttachment, FormData>(`/assets/${assetId}/attachments`, data)
  },

  void(attachmentId: number, version: number, reason: string) {
    return http.post<unknown, AssetAttachment>(`/attachments/${attachmentId}/void`, {
      version,
      reason,
    })
  },

  setCover(attachmentId: number, version: number) {
    return http.post<unknown, AssetAttachment>(`/attachments/${attachmentId}/cover`, {
      version,
    })
  },

  download(attachmentId: number): Promise<Blob> {
    return http.get<Blob, Blob>(`/attachments/${attachmentId}/download`, {
      responseType: 'blob',
    })
  },
}
