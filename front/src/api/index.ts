import http from './http'
import type { LoginResponse, User, UserPreferences, UserSessionRecord } from '@/types'

export const authApi = {
  login: (data: { username: string; password: string }) =>
    http.post<unknown, LoginResponse>('/auth/login', data),
  register: (data: { username: string; password: string; nickname?: string }) =>
    http.post<unknown, User>('/auth/register', data),
  me: () => http.get<unknown, User>('/users/me'),
  logout: () => http.post<unknown, null>('/auth/logout'),
  changePassword: (data: { current_password: string; new_password: string }) =>
    http.post<unknown, LoginResponse>('/users/me/password/update', data),
  preferences: () => http.get<unknown, UserPreferences>('/users/me/preferences'),
  updatePreferences: (data: Partial<Omit<UserPreferences, 'updated_at'>>) =>
    http.post<unknown, UserPreferences>('/users/me/preferences/update', data),
  sessions: () => http.get<unknown, UserSessionRecord[]>('/users/me/sessions'),
  revokeSession: (sessionId: string) =>
    http.post<unknown, { session_id: string; revoked: true }>(
      `/users/me/sessions/${sessionId}/revoke`,
    ),
}

export const helloApi = {
  hello: () => http.get<unknown, string>('/hello'),
}
