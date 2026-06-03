import { useCallback, useEffect, useRef } from 'react'
import { kekeApi } from '@/api'
import type { KekeEventName } from '@/types'
import { detectUA, getDeviceId, getFromTag } from '@/utils/keke/device'

const VISIT_SENT_KEY = 'keke_visit_sent'

interface TrackExtras {
  keyword?: string
  duration_ms?: number
}

/**
 * Send a Keke analytics event. Always silent — caller never has to
 * try/catch; failures are swallowed inside the API layer + here.
 */
export function useTrackEvent() {
  return useCallback((event: KekeEventName, extras?: TrackExtras) => {
    void kekeApi
      .track({
        event,
        device_id: getDeviceId(),
        from: getFromTag(),
        ua: detectUA(),
        ...extras,
      })
      .catch(() => {
        /* analytics must never break the user flow */
      })
  }, [])
}

function isVisitAlreadySent(): boolean {
  try {
    return localStorage.getItem(VISIT_SENT_KEY) === '1'
  } catch {
    return false
  }
}

function markVisitSent(): void {
  try {
    localStorage.setItem(VISIT_SENT_KEY, '1')
  } catch {
    /* localStorage disabled — accept that we'll resend visit next time */
  }
}

/**
 * Fire `visit` exactly once per browser, ever.
 *
 * - First load: hits POST /api/keke/track (which also upserts a row in
 *   the `devices` table on the server) and persists keke_visit_sent.
 * - Subsequent loads: short-circuits before any network call.
 * - StrictMode double-effect: ref guard collapses the second run.
 *
 * Clearing localStorage resets the gate, which is the only way users
 * can re-trigger device registration on the same browser.
 */
export function useTrackVisit(): void {
  const track = useTrackEvent()
  const handled = useRef(false)

  useEffect(() => {
    if (handled.current) return
    handled.current = true
    if (isVisitAlreadySent()) return
    track('visit')
    markVisitSent()
  }, [track])
}
