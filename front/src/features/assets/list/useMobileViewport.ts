import { useEffect, useState } from 'react'

const mobileViewportQuery = '(max-width: 767px)'

function readMobileViewport(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia(mobileViewportQuery).matches
}

export default function useMobileViewport(): boolean {
  const [isMobile, setIsMobile] = useState(readMobileViewport)

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined

    const mediaQuery = window.matchMedia(mobileViewportQuery)
    const handleChange = (event: MediaQueryListEvent) => setIsMobile(event.matches)

    setIsMobile(mediaQuery.matches)
    if (
      typeof mediaQuery.addEventListener === 'function' &&
      typeof mediaQuery.removeEventListener === 'function'
    ) {
      mediaQuery.addEventListener('change', handleChange)
      return () => mediaQuery.removeEventListener('change', handleChange)
    }

    if (
      typeof mediaQuery.addListener === 'function' &&
      typeof mediaQuery.removeListener === 'function'
    ) {
      mediaQuery.addListener(handleChange)
      return () => mediaQuery.removeListener(handleChange)
    }

    return undefined
  }, [])

  return isMobile
}
