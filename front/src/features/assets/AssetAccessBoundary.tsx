import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import StatePanel from '@/components/ui/StatePanel'
import { canCreateAsset, canViewAssets } from '@/features/assets/assetModel'
import { useAuthStore } from '@/store/auth'

interface AssetAccessBoundaryProps {
  access: 'view' | 'create'
  children: ReactNode
}

export default function AssetAccessBoundary({ access, children }: AssetAccessBoundaryProps) {
  const { t } = useTranslation()
  const permissions = useAuthStore((state) => state.user?.permissions)
  const canAccess = access === 'create' ? canCreateAsset(permissions) : canViewAssets(permissions)

  if (!canAccess) {
    return <StatePanel mode="empty" message={t('assets.detail.notFound')} />
  }

  return <>{children}</>
}
