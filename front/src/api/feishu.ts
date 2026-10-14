import http from '@/api/http'
import type { LoginResponse } from '@/types'

export interface FeishuLoginUrl {
  authorize_url: string
}

export interface FeishuSyncResult {
  departments?: number
  users?: number
}

export const feishuApi = {
  loginUrl: () => http.get<unknown, FeishuLoginUrl>('/feishu/login-url'),
  exchange: (code: string) => http.post<unknown, LoginResponse>('/feishu/login/exchange', { code }),
  syncAll: () => http.post<unknown, FeishuSyncResult>('/feishu/sync'),
}
