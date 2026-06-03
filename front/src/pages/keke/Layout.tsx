import { Outlet } from 'react-router-dom'
import { useTrackVisit } from './hooks/useTrackVisit'
import './keke.css'

/**
 * Shell for the public /keke/* routes.
 * - Wraps everything in `.keke-scope` so the ported H5 CSS doesn't leak
 *   into antd-styled scaffold pages.
 * - Fires the `visit` analytics event exactly once per mount.
 */
export default function KekeLayout() {
  useTrackVisit()
  return (
    <div className="keke-scope">
      <Outlet />
    </div>
  )
}
