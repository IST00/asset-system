import { Navigate, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuthStore } from '@/store/auth'
import { canAccessProtectedRoute } from './protectedRouteModel'

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const token = useAuthStore((s) => s.token)
  const location = useLocation()
  const canAccess = canAccessProtectedRoute(token)

  if (!canAccess) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }
  return <>{children}</>
}
