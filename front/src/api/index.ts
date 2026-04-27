import http from './http'
import type { LoginResponse, User } from '@/types'

export const authApi = {
  login: (data: { username: string; password: string }) =>
    http.post<unknown, LoginResponse>('/auth/login', data),
  register: (data: { username: string; password: string; nickname?: string }) =>
    http.post<unknown, User>('/auth/register', data),
  me: () => http.get<unknown, User>('/users/me'),
}

export const helloApi = {
  hello: () => http.get<unknown, string>('/hello'),
}
