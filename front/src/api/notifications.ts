import http from '@/api/http'

export interface UserNotification {
  id: number
  notification_type: string
  title: string
  content: string
  related_operation_id: number | null
  related_asset_id: number | null
  read_at: string | null
  created_at: string
}

export interface NotificationPage {
  items: UserNotification[]
  total: number
  page: number
  size: number
}

export const notificationsApi = {
  page: (params?: { page?: number; size?: number; unread_only?: boolean }) =>
    http.get<unknown, NotificationPage>('/notifications', { params }),
  unreadCount: () => http.get<unknown, number>('/notifications/unread-count'),
  markRead: (id: number) => http.post<unknown, UserNotification>(`/notifications/${id}/read`),
  markAllRead: () => http.post<unknown, number>('/notifications/read-all'),
}
