import http from '@/api/http'

export type AssetAttachmentType =
  | 'PHOTO'
  | 'CONTRACT'
  | 'INVOICE'
  | 'ACCEPTANCE'
  | 'REPAIR'
  | 'SCRAP'
  | 'OTHER'

export interface AssetAttachment {
  id: number
  asset_id: number
  business_type: AssetAttachmentType
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

export const attachmentApi = {
  list(assetId: number): Promise<AssetAttachment[]> {
    return http.get(`/assets/${assetId}/attachments`)
  },

  upload(assetId: number, businessType: AssetAttachmentType, file: File) {
    const data = new FormData()
    data.append('business_type', businessType)
    data.append('file', file)
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
