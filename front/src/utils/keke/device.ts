/**
 * Keke H5 device-level identity & runtime tags.
 * Ported from the original H5 (frontend/index.html § getDeviceId / getFromTag / detectUA).
 *
 * All three functions are idempotent and persist to localStorage so the
 * five-step funnel (visit → save_success) stays attributable to one
 * device across page reloads.
 */

const DEVICE_ID_KEY = 'keke_device_id'
const FROM_KEY = 'keke_from'

const DEVICE_ID_PATTERN = /^[a-z0-9]{16,64}$/

function safeRead(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function safeWrite(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* localStorage disabled — best effort only */
  }
}

export function getDeviceId(): string {
  const existing = safeRead(DEVICE_ID_KEY)
  if (existing && DEVICE_ID_PATTERN.test(existing)) {
    return existing
  }
  // Time prefix + double random — 32 chars, lowercase alnum.
  const random = Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2)
  const fresh = (Date.now().toString(36) + random).slice(0, 32)
  safeWrite(DEVICE_ID_KEY, fresh)
  return fresh
}

export function getFromTag(): string {
  try {
    const urlFrom = new URLSearchParams(window.location.search).get('from')
    if (urlFrom) {
      const clean = urlFrom.replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 32)
      if (clean) {
        safeWrite(FROM_KEY, clean)
        return clean
      }
    }
  } catch {
    /* URLSearchParams unavailable — fall back to storage */
  }
  return safeRead(FROM_KEY) ?? 'direct'
}

export function detectUA(): string {
  const ua = navigator.userAgent ?? ''
  if (/MicroMessenger/i.test(ua)) return 'WeChat'
  if (/iPhone|iPad|iPod/i.test(ua)) return 'iPhone'
  if (/Android/i.test(ua)) return 'Android'
  return 'other'
}
