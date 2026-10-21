export interface ApiResult<T> {
  code: number
  message: string
  data: T
  request_id?: string
}

export interface PageResult<T> {
  records: T[]
  total: number
  page: number
  size: number
}

export interface User {
  id: number
  username: string
  nickname?: string
  role?: string
  roles?: string[]
  organization_id?: number | null
  organization_path?: string | null
  permissions?: string[]
  enabled?: boolean
  created_at?: string
  updated_at?: string
  must_change_password?: boolean
  password_changed_at?: string | null
  last_login_at?: string | null
}

export interface LoginResponse {
  token: string
  tokenType?: string
  user: User
  session_expires_at?: string
  idle_timeout_minutes?: number
}

export interface UserPreferences {
  asset_list_columns: string[]
  asset_list_page_size: 20 | 50 | 100
  task_notice: boolean
  approval_notice: boolean
  weekly_digest: boolean
  updated_at?: string | null
}

export interface UserSessionRecord {
  session_id: string
  current: boolean
  active: boolean
  issued_at: string
  last_seen_at: string
  expires_at: string
  revoked_at?: string | null
  revoke_reason?: string | null
  ip_address?: string | null
  user_agent?: string | null
}
