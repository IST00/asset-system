/**
 * Resolve a Keke static asset URL against the Vite `BASE_URL` so the
 * H5 keeps working under sub-path deploys (e.g. `/scaffold/`).
 *
 * Usage:
 *   kekeAsset('hero/hero-1.jpg')          → '/keke/hero/hero-1.jpg'
 *   kekeAvatarUrl('呼噜.png')              → '/keke/avatars/%E5%91%BC...png'
 */

const ROOT = 'keke/'

function joinBase(suffix: string): string {
  const base = import.meta.env.BASE_URL || '/'
  const normalisedBase = base.endsWith('/') ? base : `${base}/`
  return `${normalisedBase}${ROOT}${suffix}`
}

export function kekeAsset(relative: string): string {
  return joinBase(relative.replace(/^\/+/, ''))
}

export function kekeAvatarUrl(file: string): string {
  return joinBase(`avatars/${encodeURIComponent(file)}`)
}
