import axios, {
  AxiosError,
  AxiosInstance,
  AxiosRequestConfig,
  AxiosResponse,
  InternalAxiosRequestConfig,
} from 'axios'
import { message } from 'antd'
import { useAuthStore } from '@/store/auth'
import type { ApiResult } from '@/types'

/**
 * 统一 axios 实例。
 *
 * baseURL 组装规则（由上到下优先）：
 *   1) VITE_API_BASE_URL       axios 的基础 URL，默认 '/api/v1'
 *   2) VITE_API_PREFIX         业务网关的固定前缀，本地开发可不配（为空字符串）
 *                              生产通过 nginx `location /<prefix>/ { proxy_pass http://back:8080/; }`
 *                              转发时 去掉 前缀再打到后端，所以后端无需配置 server.servlet.context-path。
 *
 * 业务调用方保持统一写法：`http.get('/users/me')` —— 不要自己拼前缀。
 *
 * 最终请求路径 = `${prefix}${baseURL}${url}`
 *   本地开发：  ""          + "/api/v1" + "/users/me" = "/api/v1/users/me"          （Vite 代理走 8080）
 *   生产环境：  "/scaffold" + "/api/v1" + "/users/me" = "/scaffold/api/v1/users/me" （nginx 去掉 /scaffold）
 */
const apiPrefix = (import.meta.env.VITE_API_PREFIX ?? '').replace(/\/+$/, '')
const apiBase = (import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/\/+$/, '') || '/api/v1'

/** 外部可复用：生成一个带前缀的绝对路径（给非 axios 的场景用，如 <a href>、SSE、下载）。 */
export const withApiPrefix = (path: string): string => {
  const p = path.startsWith('/') ? path : `/${path}`
  return `${apiPrefix}${p}`
}

const client: AxiosInstance = axios.create({
  baseURL: `${apiPrefix}${apiBase}`,
  timeout: 15_000,
})

client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

client.interceptors.response.use(
  (res) => res,
  (err: AxiosError<ApiResult<unknown>>) => {
    const status = err.response?.status
    const msg = err.response?.data?.message || err.message
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

const isApiResult = (value: unknown): value is ApiResult<unknown> => {
  if (!value || typeof value !== 'object' || !('code' in value)) return false
  return typeof (value as { code: unknown }).code === 'number'
}

const unwrapResponse = <Data>(response: AxiosResponse<ApiResult<Data> | Data>): Data => {
  const body = response.data
  if (!isApiResult(body)) return body
  if (body.code === 200) return body.data as Data

  message.error(body.message || 'Request failed')
  throw new Error(body.message || 'Request failed')
}

interface HttpClient {
  get<ResponsePayload = unknown, Data = ResponsePayload>(
    url: string,
    config?: AxiosRequestConfig,
  ): Promise<Data>
  post<ResponsePayload = unknown, Data = ResponsePayload, RequestBody = unknown>(
    url: string,
    data?: RequestBody,
    config?: AxiosRequestConfig<RequestBody>,
  ): Promise<Data>
}

const http: HttpClient = {
  async get<ResponsePayload = unknown, Data = ResponsePayload>(
    url: string,
    config?: AxiosRequestConfig,
  ): Promise<Data> {
    const response = await client.get<ApiResult<Data> | Data>(url, config)
    return unwrapResponse(response)
  },
  async post<ResponsePayload = unknown, Data = ResponsePayload, RequestBody = unknown>(
    url: string,
    data?: RequestBody,
    config?: AxiosRequestConfig<RequestBody>,
  ): Promise<Data> {
    const response = await client.post<
      ApiResult<Data> | Data,
      AxiosResponse<ApiResult<Data> | Data>
    >(url, data, config)
    return unwrapResponse(response)
  },
}

export default http
