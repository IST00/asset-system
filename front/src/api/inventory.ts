import http from '@/api/http'

export type InventoryTaskStatus =
  | 'DRAFT'
  | 'IN_PROGRESS'
  | 'OVERDUE'
  | 'REVIEWING'
  | 'COMPLETED'
  | 'CANCELLED'
export type InventoryItemStatus = 'PENDING' | 'FOUND' | 'LOSS' | 'UNSUBMITTED' | 'EXEMPTED'
export type InventoryLocationResult = 'MATCHED' | 'DIFFERENT' | 'TEMPORARY' | null
export type InventoryReviewStatus = 'NONE' | 'AUTO_CONFIRMED' | 'PENDING' | 'RESOLVED' | 'RETURNED'

export interface InventoryCounts {
  total: number
  checked: number
  pending: number
  found: number
  loss: number
  unsubmitted: number
  exempted: number
  exceptions: number
  admin_marked: number
}

export interface InventoryTask {
  id: number
  task_no: string
  name: string
  status: InventoryTaskStatus
  stored_status: Exclude<InventoryTaskStatus, 'OVERDUE'>
  deadline_at: string
  photo_source_mode: 'CAMERA_ONLY' | 'CAMERA_OR_ALBUM'
  min_photo_count: number
  scope_filters: Record<string, number[]>
  created_by: number
  admin_user_ids: number[]
  admins: Array<{ id: number; name: string }>
  published_at?: string | null
  collection_ended_at?: string | null
  completed_at?: string | null
  cancelled_at?: string | null
  cancel_reason?: string | null
  counts: InventoryCounts
  progress: number
  can_manage: boolean
  created_at: string
  updated_at: string
}

export interface InventoryPhoto {
  id: number
  original_name: string
  mime_type: string
  size_bytes: number
  uploaded_by: number
  created_at: string
  url: string
}

export interface InventoryItem {
  id: number
  task_id: number
  asset_id: number
  asset_code: string
  asset_name: string
  asset_status_snapshot: string
  organization_id: number
  organization_name: string
  category_id: number
  category_name: string
  holder_user_id?: number | null
  holder_name?: string | null
  responsible_user_id: number
  ledger_location_id?: number | null
  ledger_location_name?: string | null
  parent_asset_id?: number | null
  parent_asset_code?: string | null
  status: InventoryItemStatus
  physical_result?: 'FOUND' | 'LOSS' | null
  location_result: InventoryLocationResult
  actual_location_id?: number | null
  actual_location_text?: string | null
  loss_reason?: string | null
  loss_description?: string | null
  borrowed_by?: string | null
  submission_method?: 'SCANNED' | 'ADMIN_MARKED' | null
  submitted_by?: number | null
  submitted_at?: string | null
  is_late: boolean
  review_status: InventoryReviewStatus
  resolution?: string | null
  resolution_reason?: string | null
  resolved_by?: number | null
  resolved_at?: string | null
  admin_mark_reason?: string | null
  photos: InventoryPhoto[]
  can_submit: boolean
  version: number
  result_version_count: number
  suite_progress?: { total: number; checked: number } | null
}

export interface InventoryOverview {
  active_tasks: number
  pending_assets: number
  exception_items: number
  completion_rate: number
  checked_assets: number
  total_assets: number
  next_deadline?: string | null
}

export interface InventoryTaskPage {
  items: InventoryTask[]
  total: number
  page: number
  size: number
}

export interface InventoryItemPage {
  items: InventoryItem[]
  total: number
  page: number
  size: number
}

export interface CreateInventoryTaskPayload {
  name: string
  deadline_at: string
  admin_user_ids: number[]
  organization_ids: number[]
  location_ids: number[]
  category_ids: number[]
  holder_user_ids: number[]
  manager_user_ids: number[]
  asset_statuses: Array<'IDLE' | 'PENDING_RECEIPT' | 'IN_USE' | 'REPAIRING'>
  public_responsible_user_id?: number
  photo_source_mode: 'CAMERA_ONLY' | 'CAMERA_OR_ALBUM'
  min_photo_count: 1 | 2 | 3
  publish: boolean
}

export interface InventoryScanResult {
  outcome:
    | 'MATCHED'
    | 'OUTSIDE_SCOPE'
    | 'OUTSIDE_ASSIGNMENT'
    | 'ALREADY_SUBMITTED'
    | 'UNKNOWN_ASSET'
  asset_code: string
  item?: InventoryItem | null
  message: string
}

export interface InventoryScanEvent {
  id: number
  scanned_value: string
  normalized_asset_code?: string | null
  asset_id?: number | null
  asset_name?: string | null
  item_id?: number | null
  outcome: Exclude<InventoryScanResult['outcome'], 'MATCHED'> | 'MATCHED'
  scanned_by: number
  scanner_name?: string | null
  created_at: string
  resolution?: 'SURPLUS' | 'IGNORED' | null
  resolution_reason?: string | null
  resolved_by?: number | null
  resolved_at?: string | null
}

export interface InventoryResultVersion {
  id: number
  version_no: number
  action: string
  reason?: string | null
  changed_by: number
  changed_by_name?: string | null
  snapshot: Record<string, unknown>
  created_at: string
}

export interface InventoryScanEventPage {
  items: InventoryScanEvent[]
  total: number
  page: number
  size: number
}

export interface SubmitInventoryPayload {
  result: 'FOUND' | 'LOSS'
  scanned_value?: string | null
  actual_location_id?: number | null
  temporary_location?: string | null
  photo_ids: number[]
  loss_reason?: string | null
  loss_description?: string | null
  borrowed_by?: string | null
}

export const inventoryApi = {
  overview: () => http.get<unknown, InventoryOverview>('/inventory/overview'),
  tasks: (status?: InventoryTaskStatus) =>
    http.get<unknown, InventoryTaskPage>('/inventory/tasks', {
      params: { page: 0, size: 100, status },
    }),
  createTask: (payload: CreateInventoryTaskPayload) =>
    http.post<unknown, InventoryTask>('/inventory/tasks', payload),
  task: (taskId: number) => http.get<unknown, InventoryTask>(`/inventory/tasks/${taskId}`),
  publish: (taskId: number) =>
    http.post<unknown, InventoryTask>(`/inventory/tasks/${taskId}/publish`),
  items: (taskId: number, status?: string) =>
    http.get<unknown, InventoryItemPage>(`/inventory/tasks/${taskId}/items`, {
      params: { page: 0, size: 500, status },
    }),
  myPendingItems: () => http.get<unknown, InventoryItem[]>('/inventory/my-pending-items'),
  scan: (taskId: number, scannedValue: string) =>
    http.post<unknown, InventoryScanResult>(`/inventory/tasks/${taskId}/scan`, {
      scanned_value: scannedValue,
    }),
  scanEvents: (taskId: number) =>
    http.get<unknown, InventoryScanEventPage>(`/inventory/tasks/${taskId}/scan-events`, {
      params: { page: 0, size: 500 },
    }),
  uploadPhoto: (taskId: number, itemId: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return http.post<unknown, InventoryPhoto>(
      `/inventory/tasks/${taskId}/items/${itemId}/photos`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
  },
  submitItem: (taskId: number, itemId: number, payload: SubmitInventoryPayload) =>
    http.post<unknown, InventoryItem>(`/inventory/tasks/${taskId}/items/${itemId}/submit`, payload),
  adminMark: (taskId: number, itemIds: number[], reason: string) =>
    http.post<unknown, InventoryTask>(`/inventory/tasks/${taskId}/admin-mark`, {
      item_ids: itemIds,
      reason,
    }),
  endCollection: (taskId: number, pendingCount: number) =>
    http.post<unknown, InventoryTask>(`/inventory/tasks/${taskId}/end-collection`, {
      confirm_unsubmitted_count: pendingCount,
    }),
  resolveItem: (taskId: number, itemId: number, resolution: string, reason: string) =>
    http.post<unknown, InventoryItem>(`/inventory/tasks/${taskId}/items/${itemId}/resolve`, {
      resolution,
      reason,
    }),
  returnItem: (taskId: number, itemId: number, reason: string) =>
    http.post<unknown, InventoryItem>(`/inventory/tasks/${taskId}/items/${itemId}/return`, {
      reason,
    }),
  reopen: (taskId: number, itemIds: number[], deadlineAt: string, reason: string) =>
    http.post<unknown, InventoryTask>(`/inventory/tasks/${taskId}/reopen`, {
      item_ids: itemIds,
      deadline_at: deadlineAt,
      reason,
    }),
  complete: (taskId: number) =>
    http.post<unknown, InventoryTask>(`/inventory/tasks/${taskId}/complete`),
  cancel: (taskId: number, reason: string) =>
    http.post<unknown, InventoryTask>(`/inventory/tasks/${taskId}/cancel`, { reason }),
  updateAdmins: (taskId: number, adminUserIds: number[], reason: string) =>
    http.post<unknown, InventoryTask>(`/inventory/tasks/${taskId}/admins`, {
      admin_user_ids: adminUserIds,
      reason,
    }),
  updateDeadline: (taskId: number, deadlineAt: string, reason: string) =>
    http.post<unknown, InventoryTask>(`/inventory/tasks/${taskId}/deadline`, {
      deadline_at: deadlineAt,
      reason,
    }),
  withdrawItem: (taskId: number, itemId: number, reason: string) =>
    http.post<unknown, InventoryItem>(`/inventory/tasks/${taskId}/items/${itemId}/withdraw`, {
      reason,
    }),
  transferResponsibility: (
    taskId: number,
    itemId: number,
    responsibleUserId: number,
    reason: string,
  ) =>
    http.post<unknown, InventoryItem>(`/inventory/tasks/${taskId}/items/${itemId}/responsible`, {
      responsible_user_id: responsibleUserId,
      reason,
    }),
  resultVersions: (taskId: number, itemId: number) =>
    http.get<unknown, InventoryResultVersion[]>(
      `/inventory/tasks/${taskId}/items/${itemId}/versions`,
    ),
  resolveSurplus: (
    taskId: number,
    eventId: number,
    resolution: 'SURPLUS' | 'IGNORED',
    reason: string,
  ) =>
    http.post<unknown, { id: number; resolution: string }>(
      `/inventory/tasks/${taskId}/scan-events/${eventId}/resolve`,
      { resolution, reason },
    ),
  sendReminders: (taskId: number, recipientUserIds: number[] = [], reminderMessage?: string) =>
    http.post<
      unknown,
      { batch_no: string; recipient_count: number; channel: string; status: string }
    >(`/inventory/tasks/${taskId}/reminders`, {
      recipient_user_ids: recipientUserIds,
      message: reminderMessage,
    }),
  report: (taskId: number) =>
    http.get<unknown, Blob>(`/inventory/tasks/${taskId}/report`, { responseType: 'blob' }),
}
