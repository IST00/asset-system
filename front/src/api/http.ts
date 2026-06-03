import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import { message } from 'antd'
import { useAuthStore } from '@/store/auth'
import type { ApiResult } from '@/types'

/**
 * 统一 axios 实例。
 *
 * baseURL 组装规则（由上到下优先）：
 *   1) VITE_API_BASE_URL       axios 的基础 URL，默认 '/api'
 *   2) VITE_API_PREFIX         业务网关的固定前缀，本地开发可不配（为空字符串）
 *                              生产通过 nginx `location /<prefix>/ { proxy_pass http://back:8080/; }`
 *                              转发时 去掉 前缀再打到后端，所以后端无需配置 server.servlet.context-path。
 *
 * 业务调用方保持统一写法：`http.get('/users/me')` —— 不要自己拼前缀。
 *
 * 最终请求路径 = `${prefix}${baseURL}${url}`
 *   本地开发：  ""          + "/api" + "/users/me" = "/api/users/me"          （Vite 代理走 8080）
 *   生产环境：  "/scaffold" + "/api" + "/users/me" = "/scaffold/api/users/me" （nginx 去掉 /scaffold）
 *
 * 静默请求：传 `{ silent: true }` 跳过 antd message 弹窗与 401 自动登出。
 * 用于埋点 / 后台轮询等不想骚扰用户的场景。失败仍 reject，调用方自己 try/catch。
 */
const apiPrefix = (import.meta.env.VITE_API_PREFIX ?? '').replace(/\/+$/, '')
const apiBase = (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/+$/, '') || '/api'

/** 外部可复用：生成一个带前缀的绝对路径（给非 axios 的场景用，如 <a href>、SSE、下载）。 */
export const withApiPrefix = (path: string): string => {
  const p = path.startsWith('/') ? path : `/${path}`
  return `${apiPrefix}${p}`
}

declare module 'axios' {
  // eslint-disable-next-line @typescript-eslint/no-empty-interface
  export interface AxiosRequestConfig {
    /** 跳过 antd message 弹窗与 401 自动登出，方便埋点等场景静默失败 */
    silent?: boolean
  }
}

const http: AxiosInstance = axios.create({
  baseURL: `${apiPrefix}${apiBase}`,
  timeout: 15_000,
})

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (res) => {
    const silent = Boolean(res.config?.silent)
    const body = res.data as ApiResult<unknown>
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code === 200) return { ...res, data: body.data }
      if (!silent) message.error(body.message || 'Request failed')
      return Promise.reject(new Error(body.message))
    }
    return res
  },
  (err: AxiosError<ApiResult<unknown>>) => {
    const silent = Boolean(err.config?.silent)
    const status = err.response?.status
    const msg = err.response?.data?.message || err.message
    if (silent) return Promise.reject(err)
    if (status === 401) {
      message.error('登录已过期，请重新登录')
      useAuthStore.getState().logout()
      window.location.href = '/login'
    } else if (status === 403) {
      message.error('无权限')
    } else {
      message.error(msg || '网络错误')
    }
    return Promise.reject(err)
  },
)

export default http
