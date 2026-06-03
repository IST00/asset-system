import type { KekeStory } from '@/types'

/**
 * Persisted local history of the last N stories.
 * Storage shape: a JSON array, newest first, capped at HISTORY_MAX.
 */

const HISTORY_KEY = 'keke_history'
export const HISTORY_MAX = 5

export function loadHistory(): KekeStory[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed as KekeStory[]
  } catch {
    return []
  }
}

export function saveToHistory(story: KekeStory): KekeStory[] {
  const list = loadHistory()
  list.unshift({ ...story, time: story.time ?? Date.now() })
  const trimmed = list.slice(0, HISTORY_MAX)
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(trimmed))
  } catch {
    /* ignore quota / privacy errors */
  }
  return trimmed
}
