import { Skeleton, Tabs } from 'antd'
import {
  ArrowLeft,
  BadgeInfo,
  ClipboardCheck,
  ClipboardList,
  FileClock,
  Image,
  Inbox,
  MapPin,
  Network,
  Pencil,
  ReceiptText,
  ScanLine,
  Trash2,
  Wrench,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { getAsset } from '@/api/assets'
import PageHeader from '@/components/ui/PageHeader'
import SectionPanel from '@/components/ui/SectionPanel'
import StatePanel from '@/components/ui/StatePanel'
import { canViewAmount, getAssetStatusMeta } from '@/features/assets/assetModel'
import type { AssetDetail as AssetDetailRecord } from '@/features/assets/types'
import { useAuthStore } from '@/store/auth'
import { formatAssetAmount, formatAssetDate, formatAssetDateTime } from './detailFormatters'
import {
  assetDetailTabs,
  getDetailFieldGroups,
  type AssetDetailTab,
  type DetailFieldGroupKey,
  type DetailFieldKey,
} from './detailModel'
import './AssetDetail.css'

const positiveIntegerPattern = /^[1-9]\d*$/

const groupIcons: Record<DetailFieldGroupKey, LucideIcon> = {
  basic: BadgeInfo,
  ownership: MapPin,
  purchase: ReceiptText,
  management: ClipboardList,
}

const tabIcons: Record<AssetDetailTab['key'], LucideIcon> = {
  basic: BadgeInfo,
  attachments: Image,
  relations: Network,
  history: FileClock,
  repairs: Wrench,
  scrap: Trash2,
  inventory: ScanLine,
  approvals: ClipboardCheck,
}

function parseAssetId(value: string | undefined): number | null {
  if (!value || !positiveIntegerPattern.test(value)) return null

  const assetId = Number(value)
  return assetId <= Number.MAX_SAFE_INTEGER ? assetId : null
}

function isAssetNotFoundError(error: unknown): error is Error {
  return error instanceof Error && error.message === 'ASSET_NOT_FOUND'
}

function AssetDetailSkeleton() {
  const { t } = useTranslation()

  return (
    <div className="asset-detail" aria-busy="true" aria-label={t('assets.detail.loading')}>
      <PageHeader title={t('assets.detail.title')} />
      <div className="asset-detail__skeleton-heading">
        <Skeleton active paragraph={{ rows: 2 }} title={{ width: '42%' }} />
      </div>
      <div className="asset-detail__skeleton-panels">
        {[0, 1].map((item) => (
          <div key={item}>
            <Skeleton active paragraph={{ rows: 5 }} title={{ width: '28%' }} />
          </div>
        ))}
      </div>
    </div>
  )
}

function DetailPageState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useTranslation()

  return (
    <div className="asset-detail">
      <PageHeader
        title={t('assets.detail.title')}
        actions={
          <Link className="asset-detail__action-link" to="/assets">
            <ArrowLeft aria-hidden="true" size={16} />
            <span>{t('assets.detail.actions.back')}</span>
          </Link>
        }
      />
      <StatePanel
        mode={onRetry ? 'error' : 'empty'}
        message={message}
        retryLabel={onRetry ? t('assets.detail.actions.retry') : undefined}
        onRetry={onRetry}
      />
    </div>
  )
}

function EmptyTab({ tab }: { tab: AssetDetailTab }) {
  const { t } = useTranslation()
  const Icon = tabIcons[tab.key]

  return (
    <SectionPanel title={t(tab.labelKey)} icon={<Icon aria-hidden="true" size={18} />}>
      <div className="asset-detail__empty-tab" role="status">
        <Inbox aria-hidden="true" size={32} strokeWidth={1.6} />
        <p>{t('assets.detail.emptyTab')}</p>
      </div>
    </SectionPanel>
  )
}

function DetailField({ asset, field }: { asset: AssetDetailRecord; field: DetailFieldKey }) {
  const { t, i18n } = useTranslation()
  const locale = i18n.resolvedLanguage || 'zh-CN'
  const rawValue = asset[field]
  let value: ReactNode = t('assets.detail.emptyValue')

  if (field === 'status') {
    const meta = getAssetStatusMeta(asset.status)
    value = (
      <span className={`asset-detail__badge asset-detail__badge--${meta.tone}`}>
        {t(meta.labelKey)}
      </span>
    )
  } else if (field === 'information_complete') {
    value = asset.information_complete ? t('assets.detail.complete') : t('assets.detail.incomplete')
  } else if (field === 'purchase_amount') {
    value = formatAssetAmount(asset.purchase_amount, locale)
  } else if (field === 'purchase_date') {
    value = formatAssetDate(asset.purchase_date, locale)
  } else if ((field === 'created_at' || field === 'updated_at') && typeof rawValue === 'string') {
    value = formatAssetDateTime(rawValue, locale)
  } else if (typeof rawValue === 'string' && rawValue.length > 0) {
    value = rawValue
  }

  return (
    <div className={`asset-detail__field asset-detail__field--${field}`}>
      <dt>{t(`assets.detail.fields.${field}`)}</dt>
      <dd>{value}</dd>
    </div>
  )
}

function BasicInformation({
  asset,
  showAmount,
}: {
  asset: AssetDetailRecord
  showAmount: boolean
}) {
  const { t } = useTranslation()
  const groups = getDetailFieldGroups(showAmount)

  return (
    <div className="asset-detail__groups">
      {groups.map((group) => {
        const Icon = groupIcons[group.key]
        return (
          <SectionPanel
            key={group.key}
            title={t(group.titleKey)}
            icon={<Icon aria-hidden="true" size={18} />}
          >
            <dl className="asset-detail__fields">
              {group.fields.map((field) => (
                <DetailField key={field} asset={asset} field={field} />
              ))}
            </dl>
          </SectionPanel>
        )
      })}
    </div>
  )
}

function AssetDetailContent({ asset }: { asset: AssetDetailRecord }) {
  const { t } = useTranslation()
  const permissions = useAuthStore((state) => state.user?.permissions)
  const statusMeta = getAssetStatusMeta(asset.status)
  const showAmount = canViewAmount(permissions)
  const tabItems = assetDetailTabs.map((tab) => ({
    key: tab.key,
    label: t(tab.labelKey),
    children:
      tab.key === 'basic' ? (
        <BasicInformation asset={asset} showAmount={showAmount} />
      ) : (
        <EmptyTab tab={tab} />
      ),
  }))

  return (
    <div className="asset-detail">
      <PageHeader
        title={`${asset.asset_code} · ${asset.asset_name}`}
        description={t('assets.detail.title')}
        meta={
          <div className="asset-detail__meta">
            <span className={`asset-detail__badge asset-detail__badge--${statusMeta.tone}`}>
              {t(statusMeta.labelKey)}
            </span>
            <span>{asset.category_name}</span>
            <span>{asset.company_name}</span>
          </div>
        }
        actions={
          <div className="asset-detail__actions">
            <Link className="asset-detail__action-link" to="/assets">
              <ArrowLeft aria-hidden="true" size={16} />
              <span>{t('assets.detail.actions.back')}</span>
            </Link>
            <Link
              className="asset-detail__action-link asset-detail__action-link--primary"
              to={`/assets/${asset.id}/edit`}
            >
              <Pencil aria-hidden="true" size={16} />
              <span>{t('assets.detail.actions.edit')}</span>
            </Link>
          </div>
        }
      />

      <div className="asset-detail__tabs">
        <Tabs defaultActiveKey="basic" items={tabItems} />
      </div>
    </div>
  )
}

export default function AssetDetail() {
  const { t } = useTranslation()
  const { assetId: assetIdParam } = useParams()
  const assetId = parseAssetId(assetIdParam)
  const query = useQuery({
    queryKey: ['assets', 'detail', assetId],
    queryFn: () =>
      assetId === null ? Promise.reject(new Error('INVALID_ASSET_ID')) : getAsset(assetId),
    enabled: assetId !== null,
    retry: false,
  })

  if (assetId === null) return <DetailPageState message={t('assets.detail.notFound')} />
  if (query.isLoading) return <AssetDetailSkeleton />
  if (query.isError) {
    if (isAssetNotFoundError(query.error)) {
      return <DetailPageState message={t('assets.detail.notFound')} />
    }
    return (
      <DetailPageState message={t('assets.detail.error')} onRetry={() => void query.refetch()} />
    )
  }
  if (!query.data) return <DetailPageState message={t('assets.detail.notFound')} />

  return <AssetDetailContent asset={query.data} />
}
