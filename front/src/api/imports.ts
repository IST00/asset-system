import http from '@/api/http'

export type ImportType = 'ASSET' | 'ORGANIZATION' | 'CATEGORY'
export type ImportStatus = 'PREVIEW_READY' | 'VALIDATION_FAILED' | 'CONFIRMED'
export type ImportAction = 'CREATE' | 'UPDATE' | 'UNCHANGED'

export interface ImportPreviewRow {
  line: number
  action: ImportAction
  values: Record<string, string>
  errors: string[]
  warnings: string[]
  auto_actions?: string[]
}

export interface ImportJob {
  id: number
  job_no: string
  import_type: ImportType
  status: ImportStatus
  original_name: string
  file_format: 'CSV' | 'XLSX'
  row_count: number
  error_count: number
  warning_count: number
  create_count: number
  update_count: number
  unchanged_count: number
  created_by: number
  confirmed_by?: number | null
  confirmed_at?: string | null
  version: number
  created_at: string
  updated_at: string
  rows?: ImportPreviewRow[]
  result?: Record<string, unknown> | null
}

export interface ImportJobPage {
  items: ImportJob[]
  total: number
  page: number
  size: number
}

export const importApi = {
  list: (page = 0, size = 20, importType?: ImportType) =>
    http.get<unknown, ImportJobPage>('/imports', {
      params: { page, size, import_type: importType },
    }),
  detail: (id: number) => http.get<unknown, ImportJob>(`/imports/${id}`),
  preview: (importType: ImportType, file: File) => {
    const body = new FormData()
    body.append('import_type', importType)
    body.append('file', file)
    return http.post<unknown, ImportJob, FormData>('/imports/preview', body)
  },
  confirm: (job: ImportJob) =>
    http.post<unknown, ImportJob>(`/imports/${job.id}/confirm`, {
      confirmed: true,
      version: job.version,
    }),
  template: (importType: ImportType) => http.getBlob(`/imports/templates/${importType}`),
  masterDataExport: (importType: Extract<ImportType, 'ORGANIZATION' | 'CATEGORY'>) =>
    http.getBlob(`/imports/master-data/${importType}/export`),
  errorReport: (id: number) => http.getBlob(`/imports/${id}/error-report`),
}
