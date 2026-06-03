import http from './http'
import type {
  KekeGenerateStoryPayload,
  KekeGenerateStoryResponse,
  KekeTrackingEventPayload,
} from '@/types'

/**
 * Keke H5 endpoints.
 * - `track` 用 silent:true，让埋点失败不打扰用户；调用方仍需 try/catch
 *   兜底 promise rejection。
 * - `generateStory` 单独把超时拉到 180s，DeepSeek 通常需要 30-60s。
 */
export const kekeApi = {
  track: (payload: KekeTrackingEventPayload) =>
    http.post<unknown, void>('/keke/track', payload, { silent: true }),
  generateStory: (payload: KekeGenerateStoryPayload) =>
    http.post<unknown, KekeGenerateStoryResponse>('/keke/story/generate', payload, {
      timeout: 180_000,
    }),
}
