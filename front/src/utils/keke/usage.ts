/**
 * Per-device daily generation cap.
 * Ported from H5 § getUsageKey / checkAndIncrementUsage / refundUsage.
 *
 * Stored as `keke_usage_YYYY-MM-DD = <count>` in localStorage. A failed
 * generation calls refundUsage() so the user isn't penalised for our
 * server error.
 */

export const DAILY_LIMIT = 5

function todayKey(): string {
  return `keke_usage_${new Date().toISOString().slice(0, 10)}`
}

function readCount(): number {
  try {
    return parseInt(localStorage.getItem(todayKey()) ?? '0', 10) || 0
  } catch {
    return 0
  }
}

export function getRemaining(): number {
  return Math.max(0, DAILY_LIMIT - readCount())
}

export function checkAndIncrementUsage(): boolean {
  const count = readCount()
  if (count >= DAILY_LIMIT) return false
  try {
    localStorage.setItem(todayKey(), String(count + 1))
  } catch {
    /* ignore */
  }
  return true
}

export function refundUsage(): void {
  const count = readCount()
  try {
    localStorage.setItem(todayKey(), String(Math.max(0, count - 1)))
  } catch {
    /* ignore */
  }
}
