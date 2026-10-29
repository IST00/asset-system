import http from '@/api/http'
import type { AssetListQuery } from '@/features/assets/types'

export type ExportJobType = 'ASSET_CSV' | 'REPAIR_CSV' | 'SCRAP_CSV' | 'LABEL_PDF'
export type ExportJobStatus = 'PROCESSING' | 'SUCCESS' | 'FAILED' | 'EXPIRED'

export interface ExportJob {
  id: number
  job_type: ExportJobType
  status: ExportJobStatus
  original_name: string
  mime_type: string
  size_bytes: number
  item_count: number
  expires_at: string
  downloaded_at?: string | null
  error_message?: string | null
  created_at: string
}

interface ExportPage {
  items: ExportJob[]
  total: number
  page: number
  size: number
}

interface ExportFilters {
  keyword?: string
  asset_codes?: string[]
  company_name?: string
  category_name?: string
  status?: string
  department_name?: string
  location_name?: string
  user_name?: string
  manager_name?: string
  supplier_name?: string
  source_name?: string
  purchase_date_from?: string
  purchase_date_to?: string
  data_completeness?: 'COMPLETE' | 'INCOMPLETE'
}

export function assetQueryToExportFilters(query: AssetListQuery): ExportFilters {
  return {
    keyword: query.keyword,
    asset_codes: query.asset_codes,
    company_name: query.company_name,
    category_name: query.category_name,
    status: query.status,
    department_name: query.department_name,
    location_name: query.location_name,
    user_name: query.user_name,
    manager_name: query.manager_name,
    supplier_name: query.supplier_name,
    source_name: query.source_name,
    purchase_date_from: query.purchase_date_from,
    purchase_date_to: query.purchase_date_to,
    data_completeness:
      query.information_complete === undefined
        ? undefined
        : query.information_complete
          ? 'COMPLETE'
          : 'INCOMPLETE',
  }
}

const saveBlob = (blob: Blob, fileName: string) => {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export const exportsApi = {
  create: (payload: { job_type: ExportJobType; asset_ids?: number[]; filters?: ExportFilters }) =>
    http.post<unknown, ExportJob>('/exports', payload),
  page: () => http.get<unknown, ExportPage>('/exports', { params: { page: 0, size: 50 } }),
  download: async (job: ExportJob) => {
    const blob = await http.getBlob(`/exports/${job.id}/download`)
    saveBlob(blob, job.original_name)
  },
}
