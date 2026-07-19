import { Button, Progress, Skeleton } from 'antd'
import {
  ArrowRight,
  Box,
  Boxes,
  CircleAlert,
  ClipboardCheck,
  Clock3,
  FileUp,
  HandCoins,
  PackageCheck,
  PackagePlus,
  PieChart,
  Printer,
  ScanLine,
  TrendingUp,
  UserRoundX,
  Warehouse,
  Wrench,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import PageHeader from '@/components/ui/PageHeader'
import MetricCard from '@/components/ui/MetricCard'
import type { MetricTone } from '@/components/ui/MetricCard'
import SectionPanel from '@/components/ui/SectionPanel'
import StatePanel from '@/components/ui/StatePanel'
import { useAuthStore } from '@/store/auth'
import { getDemoDashboardOverview } from './dashboardData'
import { calculateProgress, countActionableIssues, selectPrimaryMetrics } from './dashboardModel'
import type { DashboardIssues, DashboardOverview, DistributionTone, PrimaryMetric } from './types'
import './Dashboard.css'

const metricPresentation: Record<
  PrimaryMetric['key'],
  { icon: LucideIcon; tone: MetricTone; labelKey: string }
> = {
  total: { icon: Boxes, tone: 'brand', labelKey: 'dashboard.metrics.total' },
  idle: { icon: Warehouse, tone: 'success', labelKey: 'dashboard.metrics.idle' },
  inUse: { icon: PackageCheck, tone: 'warning', labelKey: 'dashboard.metrics.inUse' },
  repairing: { icon: Wrench, tone: 'danger', labelKey: 'dashboard.metrics.repairing' },
}

const quickActions: Array<{
  key: string
  labelKey: string
  hintKey: string
  icon: LucideIcon
  tone: DistributionTone
  permission: string
}> = [
  {
    key: 'intake',
    labelKey: 'dashboard.actions.assetIntake',
    hintKey: 'dashboard.actions.assetIntakeHint',
    icon: PackagePlus,
    tone: 'brand',
    permission: 'asset:create',
  },
  {
    key: 'import',
    labelKey: 'dashboard.actions.excelImport',
    hintKey: 'dashboard.actions.excelImportHint',
    icon: FileUp,
    tone: 'success',
    permission: 'asset:import',
  },
  {
    key: 'inventory',
    labelKey: 'dashboard.actions.createInventory',
    hintKey: 'dashboard.actions.createInventoryHint',
    icon: ScanLine,
    tone: 'warning',
    permission: 'inventory:create',
  },
  {
    key: 'labels',
    labelKey: 'dashboard.actions.printLabels',
    hintKey: 'dashboard.actions.printLabelsHint',
    icon: Printer,
    tone: 'purple',
    permission: 'asset:label:print',
  },
]

const issuePresentation: Array<{
  key: keyof DashboardIssues
  labelKey: string
  icon: LucideIcon
  tone: DistributionTone
}> = [
  {
    key: 'pendingApprovals',
    labelKey: 'dashboard.issues.pendingApprovals',
    icon: ClipboardCheck,
    tone: 'warning',
  },
  {
    key: 'inventoryExceptions',
    labelKey: 'dashboard.issues.inventoryExceptions',
    icon: CircleAlert,
    tone: 'danger',
  },
  {
    key: 'incompleteAssets',
    labelKey: 'dashboard.issues.incompleteAssets',
    icon: Box,
    tone: 'brand',
  },
  {
    key: 'departedOwnerAssets',
    labelKey: 'dashboard.issues.departedOwnerAssets',
    icon: UserRoundX,
    tone: 'purple',
  },
]

function DashboardSkeleton() {
  const { t } = useTranslation()
  return (
    <div className="asset-dashboard" aria-label={t('dashboard.loading')} aria-busy="true">
      <PageHeader title={t('dashboard.title')} description={t('dashboard.description')} />
      <div className="asset-dashboard__skeleton-grid">
        {[0, 1, 2, 3].map((item) => (
          <div key={item} className="asset-dashboard__skeleton-card">
            <Skeleton active paragraph={{ rows: 2 }} title={{ width: '45%' }} />
          </div>
        ))}
      </div>
    </div>
  )
}

function DistributionList({
  items,
}: {
  items: Array<{ name: string; value: number; tone: DistributionTone }>
}) {
  const maxValue = Math.max(1, ...items.map((item) => item.value))

  return (
    <div className="asset-dashboard__distribution-list">
      {items.map((item) => (
        <div key={item.name} className="asset-dashboard__distribution-row">
          <div className="asset-dashboard__distribution-label">
            <span>{item.name}</span>
            <strong>{item.value}</strong>
          </div>
          <div className="asset-dashboard__distribution-track">
            <span
              className={`asset-dashboard__distribution-fill is-${item.tone}`}
              style={{ width: `${Math.round((item.value / maxValue) * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

function DashboardContent({ overview }: { overview: DashboardOverview }) {
  const { t } = useTranslation()
  const user = useAuthStore((state) => state.user)
  const [feedback, setFeedback] = useState<string | null>(null)
  const hasExplicitPermissions = Array.isArray(user?.permissions)
  const permissions = useMemo(() => new Set(user?.permissions ?? []), [user?.permissions])
  const visibleActions = quickActions.filter(
    (action) => !hasExplicitPermissions || permissions.has(action.permission),
  )
  const metrics = selectPrimaryMetrics(overview.metrics)
  const progress = calculateProgress(overview.inventory)
  const pending = Math.max(overview.inventory.total - overview.inventory.checked, 0)
  const maxMonthlyValue = overview.monthlyChanges.reduce(
    (currentMax, item) => Math.max(currentMax, item.intake, item.scrapped),
    1,
  )

  const showFeedback = (label: string) => {
    setFeedback(t('dashboard.feedback', { action: label }))
  }

  return (
    <div className="asset-dashboard">
      <PageHeader
        title={t('dashboard.title')}
        description={t('dashboard.description')}
        meta={
          <span className="asset-dashboard__updated-at">
            <Clock3 aria-hidden="true" size={14} />
            <span>{t('dashboard.updatedAt', { time: '2026-07-17 14:30' })}</span>
          </span>
        }
      />

      {feedback ? (
        <div className="asset-dashboard__feedback" role="status" aria-live="polite">
          {feedback}
        </div>
      ) : null}

      <div className="asset-dashboard__metric-grid">
        {metrics.map((metric) => {
          const presentation = metricPresentation[metric.key]
          return (
            <div key={metric.key} className="asset-dashboard__metric-cell">
              <MetricCard
                icon={presentation.icon}
                label={t(presentation.labelKey)}
                value={metric.value}
                unit={t('common.unit')}
                tone={presentation.tone}
              />
            </div>
          )
        })}
      </div>

      <div className="asset-dashboard__primary-row">
        <div className="asset-dashboard__primary-main">
          <SectionPanel
            title={t('dashboard.sections.quickActions')}
            icon={<TrendingUp size={18} />}
          >
            <div className="asset-dashboard__quick-actions">
              {visibleActions.map((action) => {
                const Icon = action.icon
                const label = t(action.labelKey)
                return (
                  <button
                    key={action.key}
                    type="button"
                    className={`asset-dashboard__quick-action is-${action.tone}`}
                    onClick={() => showFeedback(label)}
                  >
                    <span className="asset-dashboard__quick-action-icon">
                      <Icon aria-hidden="true" size={21} strokeWidth={1.8} />
                    </span>
                    <strong>{label}</strong>
                    <small>{t(action.hintKey)}</small>
                  </button>
                )
              })}
            </div>
          </SectionPanel>
        </div>

        <div className="asset-dashboard__primary-aside">
          <SectionPanel
            title={t('dashboard.sections.pendingItems')}
            icon={<ClipboardCheck size={18} />}
            extra={
              <span className="asset-dashboard__issue-total">
                {countActionableIssues(overview.issues)}
              </span>
            }
          >
            <div className="asset-dashboard__issue-list">
              {issuePresentation.map((issue) => {
                const Icon = issue.icon
                const label = t(issue.labelKey)
                return (
                  <button key={issue.key} type="button" onClick={() => showFeedback(label)}>
                    <span className={`asset-dashboard__issue-icon is-${issue.tone}`}>
                      <Icon aria-hidden="true" size={18} strokeWidth={1.8} />
                    </span>
                    <span>{label}</span>
                    <strong>{overview.issues[issue.key]}</strong>
                    <ArrowRight aria-hidden="true" size={16} />
                  </button>
                )
              })}
            </div>
          </SectionPanel>
        </div>
      </div>

      <div className="asset-dashboard__secondary-row">
        <div className="asset-dashboard__secondary-narrow">
          <SectionPanel title={t('dashboard.sections.inventory')} icon={<ScanLine size={18} />}>
            <div className="asset-dashboard__inventory-heading">
              <div>
                <strong>{overview.inventory.taskName}</strong>
                <span>{t('dashboard.inventory.completion')}</span>
              </div>
              <b>{progress}%</b>
            </div>
            <Progress percent={progress} showInfo={false} strokeWidth={9} />
            <div className="asset-dashboard__inventory-stats">
              <div>
                <strong>{overview.inventory.checked}</strong>
                <span>{t('dashboard.inventory.checked')}</span>
              </div>
              <div>
                <strong>{pending}</strong>
                <span>{t('dashboard.inventory.pending')}</span>
              </div>
              <div className="is-danger">
                <strong>{overview.inventory.exceptions}</strong>
                <span>{t('dashboard.inventory.exceptions')}</span>
              </div>
            </div>
            <Button
              type="primary"
              block
              onClick={() => showFeedback(t('dashboard.inventory.enterTask'))}
            >
              {t('dashboard.inventory.enterTask')}
            </Button>
          </SectionPanel>
        </div>

        <div className="asset-dashboard__secondary-wide">
          <SectionPanel title={t('dashboard.sections.categories')} icon={<PieChart size={18} />}>
            <DistributionList items={overview.categories} />
          </SectionPanel>
        </div>
      </div>

      <div className="asset-dashboard__statistics-row">
        <div className="asset-dashboard__statistics-wide">
          <SectionPanel
            title={t('dashboard.sections.monthlyTrend')}
            icon={<TrendingUp size={18} />}
          >
            <div className="asset-dashboard__chart-legend">
              <span className="is-brand">{t('dashboard.trend.intake')}</span>
              <span className="is-danger">{t('dashboard.trend.scrapped')}</span>
            </div>
            <div className="asset-dashboard__bar-chart">
              {overview.monthlyChanges.map((item) => (
                <div key={item.month} className="asset-dashboard__bar-group">
                  <div className="asset-dashboard__bars">
                    <span
                      className="is-brand"
                      title={`${t('dashboard.trend.intake')} ${item.intake}`}
                      style={{ height: `${Math.max(8, (item.intake / maxMonthlyValue) * 100)}%` }}
                    />
                    <span
                      className="is-danger"
                      title={`${t('dashboard.trend.scrapped')} ${item.scrapped}`}
                      style={{ height: `${Math.max(8, (item.scrapped / maxMonthlyValue) * 100)}%` }}
                    />
                  </div>
                  <small>{item.month}</small>
                </div>
              ))}
            </div>
          </SectionPanel>
        </div>

        <div className="asset-dashboard__statistics-narrow">
          <SectionPanel title={t('dashboard.sections.status')} icon={<HandCoins size={18} />}>
            <div className="asset-dashboard__status-total">
              <strong>{overview.metrics.total}</strong>
              <span>{t('dashboard.metrics.total')}</span>
            </div>
            <div
              className="asset-dashboard__status-bar"
              aria-label={t('dashboard.sections.status')}
            >
              {overview.statuses.map((item) => (
                <span
                  key={item.key}
                  className={`is-${item.tone}`}
                  style={{ width: `${(item.value / overview.metrics.total) * 100}%` }}
                />
              ))}
            </div>
            <div className="asset-dashboard__status-list">
              {overview.statuses.map((item) => (
                <div key={item.key}>
                  <span className={`is-${item.tone}`} />
                  <small>{t(`dashboard.metrics.${item.key}`)}</small>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>
          </SectionPanel>
        </div>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const { t } = useTranslation()
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['dashboard', 'overview'],
    queryFn: getDemoDashboardOverview,
  })

  if (isLoading) return <DashboardSkeleton />
  if (isError) {
    return (
      <StatePanel
        mode="error"
        message={t('dashboard.error')}
        retryLabel={t('common.retry')}
        onRetry={() => void refetch()}
      />
    )
  }
  if (!data || data.metrics.total === 0) {
    return <StatePanel mode="empty" message={t('dashboard.empty')} />
  }

  return <DashboardContent overview={data} />
}
