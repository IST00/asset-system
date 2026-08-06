import { Button, Form, Input, Modal, Select, Skeleton, Spin, Tabs, Upload, message } from 'antd'
import {
  ArrowLeft,
  BadgeInfo,
  ClipboardCheck,
  ClipboardList,
  Ban,
  Download,
  FileClock,
  FileImage,
  FileText,
  MapPin,
  Network,
  Workflow,
  ReceiptText,
  ScanLine,
  Star,
  UploadCloud,
  Trash2,
  Wrench,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { assetManagementApi } from '@/api/assetManagement'
import { attachmentApi, type AssetAttachment, type AssetAttachmentType } from '@/api/attachments'
import {
  getAsset,
  getAssetLifecycle,
  getAssetRelatedRecords,
  listAssets,
  type AssetInventoryRecord,
  type AssetLifecycleRecord,
  type AssetOperationRecord,
} from '@/api/assets'
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

const lifecycleTypeLabels: Record<string, string> = {
  STOCK_IN: '资产入库',
  PERSONAL_USE: '个人领用',
  PUBLIC_USE: '公共领用',
  PERSONAL_RETURN: '个人退库',
  PUBLIC_RETURN: '公共退库',
  TRANSFER: '资产调拨',
  REPAIR_START: '发起维修',
  REPAIR_COMPLETE: '维修完成',
  DATA_COMPLETION: '资料补录',
  ASSET_EDIT: '资料修改',
  ASSET_RELATION_ATTACH: '挂接附属资产',
  ASSET_RELATION_DETACH: '解除主附关系',
  SCRAP: '资产报废',
}

interface LifecycleQueryProps {
  records?: AssetLifecycleRecord[]
  isLoading: boolean
  isError: boolean
  onRetry: () => void
}

function LifecycleTab({ records, isLoading, isError, onRetry }: LifecycleQueryProps) {
  if (isLoading) {
    return (
      <div className="asset-detail__timeline-loading">
        <Spin />
      </div>
    )
  }
  if (isError) {
    return (
      <StatePanel
        mode="error"
        message="资产生命周期加载失败"
        retryLabel="重新加载"
        onRetry={onRetry}
      />
    )
  }
  if (!records?.length) {
    return <StatePanel mode="empty" message="当前资产暂无生命周期记录" />
  }

  return (
    <SectionPanel title="生命周期轨迹" icon={<FileClock aria-hidden="true" size={18} />}>
      <div className="asset-detail__timeline">
        {records.map((record) => (
          <article key={record.id} className="asset-detail__timeline-item">
            <span className="asset-detail__timeline-dot" aria-hidden="true" />
            <div>
              <strong>{lifecycleTypeLabels[record.operation_type] ?? record.operation_type}</strong>
              <p>{record.remark || '该操作未填写补充说明'}</p>
              <small>
                {record.operation_no} · 操作人 #{record.operator_id} ·{' '}
                {formatAssetDateTime(record.created_at, 'zh-CN')}
              </small>
            </div>
          </article>
        ))}
      </div>
    </SectionPanel>
  )
}

interface RelationFormValues {
  child_ids: number[]
  reason: string
}

function RelationsTab({ asset }: { asset: AssetDetailRecord }) {
  const permissions = useAuthStore((state) => state.user?.permissions)
  const canManage = permissions?.includes('asset:relation:manage') ?? false
  const [mode, setMode] = useState<'attach' | 'detach' | null>(null)
  const [form] = Form.useForm<RelationFormValues>()
  const queryClient = useQueryClient()
  const relationQuery = useQuery({
    queryKey: ['assets', 'relations', asset.id],
    queryFn: () => assetManagementApi.relations(asset.id),
  })
  const candidateQuery = useQuery({
    queryKey: ['assets', 'relation-candidates'],
    queryFn: () => listAssets({ page: 1, size: 100 }),
    enabled: canManage,
  })
  const relation = relationQuery.data
  const candidateOptions = useMemo(() => {
    const mainId = relation?.main.id ?? asset.id
    const attachedIds = new Set(relation?.attachments.map((item) => item.id) ?? [])
    return (candidateQuery.data?.records ?? [])
      .filter(
        (item) =>
          item.id !== mainId &&
          item.status !== 'SCRAPPED' &&
          item.parent_asset_id == null &&
          !attachedIds.has(item.id),
      )
      .map((item) => ({
        value: item.id,
        label: `${item.asset_code} · ${item.asset_name}`,
      }))
  }, [asset.id, candidateQuery.data, relation])

  const mutation = useMutation({
    mutationFn: async (values: RelationFormValues) => {
      if (!mode || !relation) throw new Error('主附关系尚未加载完成')
      if (mode === 'attach') {
        return assetManagementApi.attach(relation.main.id, values.child_ids, values.reason)
      }
      return assetManagementApi.detach(relation.main.id, values.child_ids, values.reason)
    },
    onSuccess: async () => {
      await message.success(mode === 'attach' ? '附属资产已挂接' : '主附关系已解除')
      setMode(null)
      form.resetFields()
      void queryClient.invalidateQueries({ queryKey: ['assets'] })
    },
    onError: (error: Error) => void message.error(error.message),
  })

  if (relationQuery.isLoading) {
    return (
      <div className="asset-detail__timeline-loading">
        <Spin />
      </div>
    )
  }
  if (relationQuery.isError || !relation) {
    return (
      <StatePanel
        mode="error"
        message="主附资产关系加载失败"
        retryLabel="重新加载"
        onRetry={() => void relationQuery.refetch()}
      />
    )
  }

  const openModal = (nextMode: 'attach' | 'detach') => {
    setMode(nextMode)
    form.resetFields()
    form.setFieldsValue({ child_ids: [], reason: '' })
  }

  return (
    <SectionPanel title="主附资产关系" icon={<Network aria-hidden="true" size={18} />}>
      <div className="asset-detail__relation-summary">
        <div>
          <span>主资产</span>
          <Link to={`/assets/${relation.main.id}`}>
            {relation.main.asset_code} · {relation.main.asset_name}
          </Link>
        </div>
        <strong>{relation.attachments.length} 件附属资产</strong>
      </div>

      {relation.attachments.length ? (
        <div className="asset-detail__relation-list">
          {relation.attachments.map((item) => (
            <Link key={item.id} to={`/assets/${item.id}`} className="asset-detail__relation-card">
              <span>{item.asset_code}</span>
              <strong>{item.asset_name}</strong>
              <small>
                {item.location_name || '未设置地点'} · {item.user_name || '未分配使用人'}
              </small>
            </Link>
          ))}
        </div>
      ) : (
        <div className="asset-detail__empty-tab" role="status">
          <Network aria-hidden="true" size={30} strokeWidth={1.6} />
          <p>当前主资产没有附属资产</p>
        </div>
      )}

      {canManage ? (
        <div className="asset-detail__relation-actions">
          <Button type="primary" onClick={() => openModal('attach')}>
            挂接附属资产
          </Button>
          <Button disabled={!relation.attachments.length} onClick={() => openModal('detach')}>
            解除关系
          </Button>
        </div>
      ) : null}

      <Modal
        className="asset-list__modal"
        open={mode !== null}
        title={mode === 'attach' ? '挂接附属资产' : '解除主附关系'}
        okText={mode === 'attach' ? '确认挂接' : '确认解除'}
        cancelText="取消"
        confirmLoading={mutation.isPending}
        onCancel={() => setMode(null)}
        onOk={() => form.submit()}
      >
        <Form form={form} layout="vertical" onFinish={(values) => mutation.mutate(values)}>
          <Form.Item
            name="child_ids"
            label={mode === 'attach' ? '选择附属资产' : '选择要解除的资产'}
            rules={[{ required: true, message: '请至少选择一件资产' }]}
          >
            <Select
              mode="multiple"
              showSearch
              loading={candidateQuery.isLoading}
              optionFilterProp="label"
              options={
                mode === 'attach'
                  ? candidateOptions
                  : relation.attachments.map((item) => ({
                      value: item.id,
                      label: `${item.asset_code} · ${item.asset_name}`,
                    }))
              }
              placeholder="请选择资产"
            />
          </Form.Item>
          <Form.Item
            name="reason"
            label="操作原因"
            rules={[{ required: true, whitespace: true, message: '请填写操作原因' }]}
          >
            <Input.TextArea rows={4} maxLength={500} showCount placeholder="说明挂接或解除原因" />
          </Form.Item>
        </Form>
      </Modal>
    </SectionPanel>
  )
}

type RecordTone = 'blue' | 'green' | 'amber' | 'red' | 'slate'

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function nestedRecord(
  source: Record<string, unknown> | null,
  key: string,
): Record<string, unknown> | null {
  return asRecord(source?.[key])
}

function textValue(value: unknown): string | null {
  if (typeof value === 'string') return value.trim() || null
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return null
}

function fieldText(source: Record<string, unknown> | null, key: string): string | null {
  return textValue(source?.[key])
}

function formatMoneyValue(value: string | null): string {
  if (value === null) return '—'
  const amount = Number(value)
  if (!Number.isFinite(amount)) return value
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 2,
  }).format(amount)
}

function statusTone(status?: string | null): RecordTone {
  if (!status) return 'slate'
  if (
    ['APPROVED', 'SUCCESS', 'COMPLETED', 'FOUND', 'MATCHED', 'CONFIRMED', 'RESOLVED'].includes(
      status,
    )
  ) {
    return 'green'
  }
  if (['REJECTED', 'FAILED', 'LOST', 'MISMATCH', 'CANCELLED', 'TERMINATED'].includes(status)) {
    return 'red'
  }
  if (['PENDING', 'WAITING', 'RUNNING', 'IN_PROGRESS', 'RETURNED', 'REVIEWING'].includes(status)) {
    return 'amber'
  }
  return 'blue'
}

function StatusLabel({ label, status }: { label: string; status?: string | null }) {
  return (
    <span
      className={`asset-detail__record-status asset-detail__record-status--${statusTone(status)}`}
    >
      {label}
    </span>
  )
}

function RecordFact({ label, value }: { label: string; value?: ReactNode }) {
  return (
    <div className="asset-detail__record-fact">
      <span>{label}</span>
      <strong>{value || '—'}</strong>
    </div>
  )
}

function RecordsLoading() {
  return (
    <div className="asset-detail__timeline-loading">
      <Spin />
    </div>
  )
}

function LifecycleCategoryTab({
  records,
  isLoading,
  isError,
  onRetry,
  category,
  showAmount,
}: LifecycleQueryProps & {
  category: 'repairs' | 'scrap'
  showAmount: boolean
}) {
  if (isLoading) return <RecordsLoading />
  if (isError) {
    return (
      <StatePanel
        mode="error"
        message={category === 'repairs' ? '维修记录加载失败' : '报废记录加载失败'}
        retryLabel="重新加载"
        onRetry={onRetry}
      />
    )
  }

  const allowed = category === 'repairs' ? ['REPAIR_START', 'REPAIR_COMPLETE'] : ['SCRAP']
  const filtered = (records ?? []).filter((record) => allowed.includes(record.operation_type))
  if (!filtered.length) {
    return (
      <StatePanel
        mode="empty"
        message={category === 'repairs' ? '当前资产暂无维修记录' : '当前资产暂无报废记录'}
      />
    )
  }

  const Icon = category === 'repairs' ? Wrench : Trash2
  return (
    <SectionPanel
      title={category === 'repairs' ? '维修记录' : '报废记录'}
      icon={<Icon aria-hidden="true" size={18} />}
    >
      <div className="asset-detail__record-list">
        {filtered.map((record) => {
          const before = record.before_data
          const after = record.after_data
          const custom = nestedRecord(after, 'custom_attributes')
          const repair =
            nestedRecord(
              custom,
              record.operation_type === 'REPAIR_START' ? 'repair_context' : 'last_repair',
            ) ?? {}
          const scrap = nestedRecord(custom, 'scrap') ?? {}
          const amount =
            category === 'repairs'
              ? fieldText(
                  repair,
                  record.operation_type === 'REPAIR_START' ? 'estimated_cost' : 'actual_cost',
                )
              : fieldText(scrap, 'scrap_amount')
          return (
            <article key={record.id} className="asset-detail__record-card">
              <header className="asset-detail__record-card-header">
                <div className="asset-detail__record-title">
                  <span className="asset-detail__record-icon">
                    <Icon aria-hidden="true" size={18} />
                  </span>
                  <div>
                    <strong>
                      {lifecycleTypeLabels[record.operation_type] ?? record.operation_type}
                    </strong>
                    <small>{record.operation_no}</small>
                  </div>
                </div>
                <StatusLabel
                  status={fieldText(after, 'status')}
                  label={fieldText(after, 'status') ?? '已记录'}
                />
              </header>
              <div className="asset-detail__record-grid">
                <RecordFact
                  label={category === 'repairs' ? '状态变化' : '报废后状态'}
                  value={
                    category === 'repairs'
                      ? `${fieldText(before, 'status') ?? '—'} → ${fieldText(after, 'status') ?? '—'}`
                      : fieldText(after, 'status')
                  }
                />
                {category === 'repairs' ? (
                  <RecordFact
                    label={record.operation_type === 'REPAIR_START' ? '维修供应商' : '维修结果'}
                    value={
                      record.operation_type === 'REPAIR_START'
                        ? fieldText(repair, 'vendor')
                        : fieldText(repair, 'result')
                    }
                  />
                ) : (
                  <RecordFact label="报废日期" value={fieldText(scrap, 'scrap_date')} />
                )}
                <RecordFact
                  label={
                    category === 'repairs'
                      ? record.operation_type === 'REPAIR_START'
                        ? '预计费用'
                        : '实际费用'
                      : '回收金额'
                  }
                  value={showAmount ? formatMoneyValue(amount) : '无金额查看权限'}
                />
                <RecordFact
                  label="操作时间"
                  value={formatAssetDateTime(record.created_at, 'zh-CN')}
                />
              </div>
              <p className="asset-detail__record-note">
                {record.remark || (category === 'repairs' ? '未填写维修说明' : '未填写报废原因')}
              </p>
              <footer>操作人 #{record.operator_id}</footer>
            </article>
          )
        })}
      </div>
    </SectionPanel>
  )
}

const inventoryStatusLabels: Record<string, string> = {
  DRAFT: '草稿',
  PUBLISHED: '进行中',
  IN_PROGRESS: '进行中',
  COLLECTION_ENDED: '待复核',
  COMPLETED: '已完成',
  CANCELLED: '已取消',
  PENDING: '待盘点',
  FOUND: '盘盈/在场',
  LOST: '盘亏',
  MATCHED: '地点一致',
  MISMATCH: '地点不一致',
  AUTO_CONFIRMED: '自动确认',
  CONFIRMED: '已确认',
  RESOLVED: '已处理',
  RETURNED: '已退回',
  NONE: '未复核',
}

function inventoryLabel(value?: string | null): string {
  if (!value) return '—'
  return inventoryStatusLabels[value] ?? value
}

interface RelatedTabProps {
  isLoading: boolean
  isError: boolean
  onRetry: () => void
}

function InventoryRecordsTab({
  records,
  isLoading,
  isError,
  onRetry,
}: RelatedTabProps & { records?: AssetInventoryRecord[] }) {
  if (isLoading) return <RecordsLoading />
  if (isError) {
    return (
      <StatePanel
        mode="error"
        message="资产盘点记录加载失败"
        retryLabel="重新加载"
        onRetry={onRetry}
      />
    )
  }
  if (!records?.length) return <StatePanel mode="empty" message="当前资产暂无盘点记录" />

  return (
    <SectionPanel
      title="盘点记录"
      icon={<ScanLine aria-hidden="true" size={18} />}
      extra={
        <Link className="asset-detail__section-link" to="/inventory">
          打开盘点中心
        </Link>
      }
    >
      <div className="asset-detail__record-list">
        {records.map((record) => (
          <article key={record.id} className="asset-detail__record-card">
            <header className="asset-detail__record-card-header">
              <div className="asset-detail__record-title">
                <span className="asset-detail__record-icon asset-detail__record-icon--green">
                  <ScanLine aria-hidden="true" size={18} />
                </span>
                <div>
                  <strong>{record.task_name}</strong>
                  <small>{record.task_no}</small>
                </div>
              </div>
              <div className="asset-detail__record-statuses">
                <StatusLabel
                  status={record.task_status}
                  label={inventoryLabel(record.task_status)}
                />
                <StatusLabel
                  status={record.item_status}
                  label={inventoryLabel(record.item_status)}
                />
              </div>
            </header>
            <div className="asset-detail__record-grid">
              <RecordFact
                label="截止时间"
                value={formatAssetDateTime(record.deadline_at, 'zh-CN')}
              />
              <RecordFact label="实物结果" value={inventoryLabel(record.physical_result)} />
              <RecordFact label="地点结果" value={inventoryLabel(record.location_result)} />
              <RecordFact label="账面地点" value={record.ledger_location_name} />
              <RecordFact label="实际地点" value={record.actual_location_text} />
              <RecordFact label="提交人" value={record.submitted_by_name} />
              <RecordFact
                label="提交时间"
                value={
                  record.submitted_at ? formatAssetDateTime(record.submitted_at, 'zh-CN') : '—'
                }
              />
              <RecordFact label="复核状态" value={inventoryLabel(record.review_status)} />
              <RecordFact label="处理结果" value={inventoryLabel(record.resolution)} />
            </div>
            {record.loss_reason || record.loss_description || record.resolution_reason ? (
              <p className="asset-detail__record-note">
                {[record.loss_reason, record.loss_description, record.resolution_reason]
                  .filter(Boolean)
                  .join(' · ')}
              </p>
            ) : null}
            <footer>{record.is_late ? '逾期提交' : '按期记录'}</footer>
          </article>
        ))}
      </div>
    </SectionPanel>
  )
}

const approvalStatusLabels: Record<string, string> = {
  DRAFT: '草稿',
  PENDING: '审批中',
  WAITING: '等待前序',
  APPROVED: '已通过',
  REJECTED: '已拒绝',
  WITHDRAWN: '已撤回',
  NOT_STARTED: '待执行',
  RUNNING: '执行中',
  SUCCESS: '已执行',
  FAILED: '执行失败',
  TERMINATED: '已终止',
}

const approvalChannelLabels: Record<string, string> = {
  INTERNAL: '系统内审批',
  DIRECT: '直接执行',
  FEISHU: '外部审批通道',
  LOCAL_FEISHU: '本地模拟审批',
}

function approvalLabel(value: string): string {
  return approvalStatusLabels[value] ?? value
}

function ApprovalRecordsTab({
  records,
  isLoading,
  isError,
  onRetry,
}: RelatedTabProps & { records?: AssetOperationRecord[] }) {
  if (isLoading) return <RecordsLoading />
  if (isError) {
    return (
      <StatePanel
        mode="error"
        message="相关审批记录加载失败"
        retryLabel="重新加载"
        onRetry={onRetry}
      />
    )
  }
  if (!records?.length) return <StatePanel mode="empty" message="当前资产暂无相关审批记录" />

  return (
    <SectionPanel
      title="相关审批"
      icon={<ClipboardCheck aria-hidden="true" size={18} />}
      extra={
        <Link className="asset-detail__section-link" to="/approvals">
          打开审批中心
        </Link>
      }
    >
      <div className="asset-detail__record-list">
        {records.map((record) => (
          <article key={record.id} className="asset-detail__record-card">
            <header className="asset-detail__record-card-header">
              <div className="asset-detail__record-title">
                <span className="asset-detail__record-icon asset-detail__record-icon--violet">
                  <ClipboardCheck aria-hidden="true" size={18} />
                </span>
                <div>
                  <strong>
                    {lifecycleTypeLabels[record.operation_type] ?? record.operation_type}
                  </strong>
                  <small>{record.request_no}</small>
                </div>
              </div>
              <div className="asset-detail__record-statuses">
                <StatusLabel
                  status={record.approval_status}
                  label={approvalLabel(record.approval_status)}
                />
                <StatusLabel
                  status={record.execution_status}
                  label={approvalLabel(record.execution_status)}
                />
              </div>
            </header>
            <div className="asset-detail__record-grid">
              <RecordFact
                label="申请人"
                value={record.applicant_name ?? `用户 #${record.applicant_id}`}
              />
              <RecordFact
                label="审批通道"
                value={approvalChannelLabels[record.approval_channel] ?? record.approval_channel}
              />
              <RecordFact
                label="提交时间"
                value={
                  record.submitted_at ? formatAssetDateTime(record.submitted_at, 'zh-CN') : '—'
                }
              />
              <RecordFact
                label="审批时间"
                value={record.approved_at ? formatAssetDateTime(record.approved_at, 'zh-CN') : '—'}
              />
              <RecordFact
                label="执行时间"
                value={record.executed_at ? formatAssetDateTime(record.executed_at, 'zh-CN') : '—'}
              />
              <RecordFact label="审批层级" value={`${record.approval_steps.length} 层`} />
            </div>
            {record.withdrawal_reason || record.execution_error ? (
              <p className="asset-detail__record-note asset-detail__record-note--danger">
                {record.withdrawal_reason || record.execution_error}
              </p>
            ) : null}
            {record.approval_steps.length ? (
              <div className="asset-detail__approval-steps">
                {record.approval_steps.map((step) => (
                  <div key={step.id} className="asset-detail__approval-step">
                    <div className="asset-detail__approval-step-heading">
                      <strong>第 {step.level_no} 层</strong>
                      <StatusLabel status={step.status} label={approvalLabel(step.status)} />
                    </div>
                    {step.tasks.map((task) => (
                      <div key={task.id} className="asset-detail__approval-person">
                        <span>{task.approver_name ?? `审批人 #${task.approver_id}`}</span>
                        <strong>{approvalLabel(task.status)}</strong>
                        <small>{task.opinion || '未填写审批意见'}</small>
                        <small>
                          {task.decided_at
                            ? formatAssetDateTime(task.decided_at, 'zh-CN')
                            : '等待处理'}
                        </small>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            ) : (
              <p className="asset-detail__record-note">该操作无需审批层级或由系统直接执行。</p>
            )}
          </article>
        ))}
      </div>
    </SectionPanel>
  )
}

const attachmentTypeLabels: Record<AssetAttachmentType, string> = {
  PHOTO: '资产照片',
  CONTRACT: '合同',
  INVOICE: '发票',
  ACCEPTANCE: '验收资料',
  REPAIR: '维修资料',
  SCRAP: '报废资料',
  OTHER: '其他附件',
}

const attachmentTypeOptions = Object.entries(attachmentTypeLabels).map(([value, label]) => ({
  value: value as AssetAttachmentType,
  label,
}))

function formatFileSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function downloadBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function AttachmentsTab({ assetId }: { assetId: number }) {
  const permissions = useAuthStore((state) => state.user?.permissions ?? [])
  const canManage = permissions.includes('asset:attachment:manage')
  const queryClient = useQueryClient()
  const [businessType, setBusinessType] = useState<AssetAttachmentType>('PHOTO')
  const [voidTarget, setVoidTarget] = useState<AssetAttachment | null>(null)
  const [voidReason, setVoidReason] = useState('')

  const query = useQuery({
    queryKey: ['assets', 'attachments', assetId],
    queryFn: () => attachmentApi.list(assetId),
  })
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ['assets', 'attachments', assetId] })
  const uploadMutation = useMutation({
    mutationFn: (file: File) => attachmentApi.upload(assetId, businessType, file),
    onSuccess: async () => {
      await refresh()
      void message.success('附件已上传并写入资产履历')
    },
    onError: (error) => void message.error(error instanceof Error ? error.message : '附件上传失败'),
  })
  const coverMutation = useMutation({
    mutationFn: (attachment: AssetAttachment) =>
      attachmentApi.setCover(attachment.id, attachment.version),
    onSuccess: async () => {
      await refresh()
      void message.success('资产封面已更新')
    },
  })
  const voidMutation = useMutation({
    mutationFn: (attachment: AssetAttachment) =>
      attachmentApi.void(attachment.id, attachment.version, voidReason.trim()),
    onSuccess: async () => {
      setVoidTarget(null)
      setVoidReason('')
      await refresh()
      void message.success('附件已作废，历史记录仍保留')
    },
  })
  const downloadMutation = useMutation({
    mutationFn: (attachment: AssetAttachment) => attachmentApi.download(attachment.id),
    onSuccess: (blob, attachment) => downloadBlob(attachment.original_name, blob),
  })

  if (query.isLoading) {
    return (
      <div className="asset-detail__timeline-loading">
        <Spin />
      </div>
    )
  }
  if (query.isError) {
    return (
      <StatePanel
        mode="error"
        message="资产附件加载失败"
        retryLabel="重新加载"
        onRetry={() => void query.refetch()}
      />
    )
  }

  const attachments = query.data ?? []
  const activeCount = attachments.filter((item) => item.status === 'ACTIVE').length
  const photos = attachments.filter(
    (item) => item.business_type === 'PHOTO' && item.status === 'ACTIVE',
  )

  return (
    <div className="asset-attachments">
      <SectionPanel
        title="照片与业务附件"
        icon={<FileImage aria-hidden="true" size={18} />}
        extra={
          canManage ? (
            <div className="asset-attachments__upload-actions">
              <Select
                value={businessType}
                options={attachmentTypeOptions}
                onChange={setBusinessType}
                aria-label="附件类型"
              />
              <Upload
                accept={businessType === 'PHOTO' ? 'image/jpeg,image/png,image/webp' : undefined}
                showUploadList={false}
                disabled={uploadMutation.isPending}
                beforeUpload={(file) => {
                  uploadMutation.mutate(file)
                  return Upload.LIST_IGNORE
                }}
              >
                <Button
                  type="primary"
                  icon={<UploadCloud aria-hidden="true" size={16} />}
                  loading={uploadMutation.isPending}
                >
                  上传附件
                </Button>
              </Upload>
            </div>
          ) : undefined
        }
      >
        <div className="asset-attachments__summary">
          <span>有效附件 {activeCount} 个</span>
          <span>资产照片 {photos.length}/5 张</span>
          <span>文件不存数据库，下载继续校验资产权限</span>
        </div>
        {attachments.length ? (
          <div className="asset-attachments__grid">
            {attachments.map((attachment) => {
              const isImage = attachment.mime_type.startsWith('image/')
              return (
                <article
                  key={attachment.id}
                  className={`asset-attachment-card ${
                    attachment.status === 'VOIDED' ? 'asset-attachment-card--voided' : ''
                  }`}
                >
                  <span className="asset-attachment-card__icon">
                    {isImage ? <FileImage size={20} /> : <FileText size={20} />}
                  </span>
                  <div className="asset-attachment-card__content">
                    <div className="asset-attachment-card__title">
                      <strong>{attachment.original_name}</strong>
                      {attachment.is_cover ? <span>封面</span> : null}
                      {attachment.status === 'VOIDED' ? <span>已作废</span> : null}
                    </div>
                    <span>
                      {attachmentTypeLabels[attachment.business_type]} ·{' '}
                      {formatFileSize(attachment.size_bytes)}
                    </span>
                    <small>
                      上传于 {formatAssetDateTime(attachment.created_at, 'zh-CN')}
                      {attachment.void_reason ? ` · ${attachment.void_reason}` : ''}
                    </small>
                  </div>
                  <div className="asset-attachment-card__actions">
                    {attachment.status === 'ACTIVE' ? (
                      <Button
                        size="small"
                        icon={<Download size={14} />}
                        loading={
                          downloadMutation.isPending &&
                          downloadMutation.variables?.id === attachment.id
                        }
                        onClick={() => downloadMutation.mutate(attachment)}
                      >
                        下载
                      </Button>
                    ) : null}
                    {canManage &&
                    attachment.status === 'ACTIVE' &&
                    attachment.business_type === 'PHOTO' &&
                    !attachment.is_cover ? (
                      <Button
                        size="small"
                        icon={<Star size={14} />}
                        loading={
                          coverMutation.isPending && coverMutation.variables?.id === attachment.id
                        }
                        onClick={() => coverMutation.mutate(attachment)}
                      >
                        设为封面
                      </Button>
                    ) : null}
                    {canManage && attachment.status === 'ACTIVE' ? (
                      <Button
                        size="small"
                        danger
                        icon={<Ban size={14} />}
                        onClick={() => setVoidTarget(attachment)}
                      >
                        作废
                      </Button>
                    ) : null}
                  </div>
                </article>
              )
            })}
          </div>
        ) : (
          <StatePanel mode="empty" message="暂无资产照片或业务附件" />
        )}
      </SectionPanel>

      <Modal
        title={`作废附件 · ${voidTarget?.original_name ?? ''}`}
        open={Boolean(voidTarget)}
        okText="确认作废"
        cancelText="取消"
        okButtonProps={{ disabled: voidReason.trim().length < 2 }}
        confirmLoading={voidMutation.isPending}
        onOk={() => {
          if (voidTarget) voidMutation.mutate(voidTarget)
        }}
        onCancel={() => {
          setVoidTarget(null)
          setVoidReason('')
        }}
      >
        <p>文件记录和审计轨迹会保留，作废后不能继续下载。</p>
        <Input.TextArea
          rows={4}
          maxLength={500}
          showCount
          value={voidReason}
          placeholder="填写作废或替换原因，至少 2 个字"
          onChange={(event) => setVoidReason(event.target.value)}
        />
      </Modal>
    </div>
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
  const lifecycleQuery = useQuery({
    queryKey: ['assets', 'lifecycle', asset.id],
    queryFn: () => getAssetLifecycle(asset.id),
  })
  const relatedQuery = useQuery({
    queryKey: ['assets', 'related-records', asset.id],
    queryFn: () => getAssetRelatedRecords(asset.id),
  })
  const lifecycleProps: LifecycleQueryProps = {
    records: lifecycleQuery.data,
    isLoading: lifecycleQuery.isLoading,
    isError: lifecycleQuery.isError,
    onRetry: () => void lifecycleQuery.refetch(),
  }
  const relatedProps: RelatedTabProps = {
    isLoading: relatedQuery.isLoading,
    isError: relatedQuery.isError,
    onRetry: () => void relatedQuery.refetch(),
  }
  const tabItems = assetDetailTabs.map((tab) => ({
    key: tab.key,
    label: t(tab.labelKey),
    children:
      tab.key === 'basic' ? (
        <BasicInformation asset={asset} showAmount={showAmount} />
      ) : tab.key === 'attachments' ? (
        <AttachmentsTab assetId={asset.id} />
      ) : tab.key === 'relations' ? (
        <RelationsTab asset={asset} />
      ) : tab.key === 'history' ? (
        <LifecycleTab {...lifecycleProps} />
      ) : tab.key === 'repairs' ? (
        <LifecycleCategoryTab {...lifecycleProps} category="repairs" showAmount={showAmount} />
      ) : tab.key === 'scrap' ? (
        <LifecycleCategoryTab {...lifecycleProps} category="scrap" showAmount={showAmount} />
      ) : tab.key === 'inventory' ? (
        <InventoryRecordsTab {...relatedProps} records={relatedQuery.data?.inventory_records} />
      ) : (
        <ApprovalRecordsTab {...relatedProps} records={relatedQuery.data?.operations} />
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
              to="/workflows"
            >
              <Workflow aria-hidden="true" size={16} />
              <span>通过流程变更</span>
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
