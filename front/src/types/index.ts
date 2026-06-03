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

// ===== Keke H5 =====

export type KekeEventName =
  | 'visit'
  | 'generate_start'
  | 'generate_success'
  | 'save_open'
  | 'save_success'

export type KekeBlockType = 'para' | 'question' | 'action' | 'predict'

export interface KekeStoryBlock {
  type: KekeBlockType
  text: string
}

export interface KekeStory {
  title: string
  keyword: string
  blocks: KekeStoryBlock[]
  time?: number
}

export type KekeCharacterGroup = '核心家庭' | '玩伴' | '城市大人'

export interface KekeCharacter {
  name: string
  file: string
  role: string
  group: KekeCharacterGroup
  desc: string
}

export interface KekeTrackingEventPayload {
  event: KekeEventName
  device_id: string
  from: string
  ua?: string
  keyword?: string
  duration_ms?: number
}

export interface KekeGenerateStoryPayload {
  device_id: string
  from: string
  ua?: string
  keyword: string
}

export interface KekeGenerateStoryResponse {
  content: string
}
