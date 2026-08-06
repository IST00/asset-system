import http from '@/api/http'

export interface SystemStatus {
  profile: string
  application: {
    name: string
    healthy: boolean
    server_time: string
  }
  database: {
    connected: boolean
    dialect: string
    label: string
  }
  feishu: {
    mode: 'FORMAL_CONFIGURED' | 'LOCAL_SIMULATION' | 'NOT_CONFIGURED'
    formal_configured: boolean
    local_simulation_available: boolean
  }
  file_storage: {
    configured: boolean
    mode: 'CONFIGURED' | 'NOT_CONFIGURED'
  }
  backup: {
    configured: boolean
    mode: 'CONFIGURED' | 'NOT_CONFIGURED'
  }
  security: {
    session_hours?: number | null
    idle_timeout_minutes: number
    login_lock_threshold: number
    login_lock_minutes: number
    login_rate_limit_per_minute: number
    user_rate_limit_per_minute: number
    login_failure_lock_configured: boolean
    rate_limit_configured: boolean
  }
}

export const systemApi = {
  status: () => http.get<unknown, SystemStatus>('/system/status'),
}
