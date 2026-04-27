export interface ApiResult<T> {
  code: number
  message: string
  data: T
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
}

export interface LoginResponse {
  token: string
  tokenType: string
  user: User
}
