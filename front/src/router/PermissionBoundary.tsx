import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import StatePanel from '@/components/ui/StatePanel'
import { useAuthStore } from '@/store/auth'

interface PermissionBoundaryProps {
  permission: string
  children: ReactNode
}

export default function PermissionBoundary({ permission, children }: PermissionBoundaryProps) {
  const { t } = useTranslation()
  const permissions = useAuthStore((state) => state.user?.permissions)

  if (!(permissions ?? []).includes(permission)) {
    return <StatePanel mode="empty" message={t('common.noPermission')} />
  }

  return <>{children}</>
}
