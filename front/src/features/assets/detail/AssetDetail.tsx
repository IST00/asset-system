import {
  Button,
  Form,
  Input,
  Modal,
  Select,
  Skeleton,
  Spin,
  Table,
  Tabs,
  Upload,
  message,
} from 'antd'
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
import type { ColumnsType } from 'antd/es/table'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, Navigate, useParams } from 'react-router-dom'
import {
  assetManagementApi,
  type AssetRepairRecord,
  type AssetScrapRecord,
} from '@/api/assetManagement'
import {
  attachmentApi,
  type AssetAttachment,
  type AssetAttachmentDocumentType,
  type AssetAttachmentType,
} from '@/api/attachments'
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
import { formatBeijingDateTime } from '@/utils/dateTime'
import {
  assetStatusLabel,
  executionStatusLabel,
  scrapDispositionLabel,
} from '@/utils/displayLabels'
import { formatAssetAmount, formatAssetDate } from './detailFormatters'
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
  STOCK_IN: '资产入账',
  PERSONAL_USE: '领用',
  PUBLIC_USE: '公共领用',
  PERSONAL_RETURN: '退库',
  PUBLIC_RETURN: '公共退库',
  TRANSFER: '资产调拨',
  REPAIR_START: '发起维修',
  REPAIR_COMPLETE: '维修完成',
  DATA_COMPLETION: '资料补录',
  ASSET_DATA_COMPLETE: '资料补录',
  ASSET_EDIT: '资料修改',
  PHYSICAL_INFO_CHANGE: '实物信息变更',
  FINANCIAL_INFO_CHANGE: '财务信息变更',
  WARRANTY_INFO_CHANGE: '保修信息变更',
  ASSET_RELATION_ATTACH: '挂接附属资产',
  ASSET_RELATION_DETACH: '解除主附关系',
  ASSET_ATTACHMENT_UPLOAD: '附件上传',
  ASSET_ATTACHMENT_VOID: '附件作废',
  ASSET_EXPORT: '资产导出',
  ASSET_LABEL_PRINT: '打印标签',
  SCRAP: '资产报废',
  INVENTORY_PROCESS: '盘点处理',
}

interface LifecycleQueryProps {
  records?: AssetLifecycleRecord[]
  isLoading: boolean
  isError: boolean
  onRetry: () => void
}

function LifecycleTab({ records, isLoading, isError, onRetry }: LifecycleQueryProps) {
  const columns: ColumnsType<AssetLifecycleRecord> = [
    {
      title: '处理日期',
      dataIndex: 'created_at',
      width: 180,
      render: (value: string) => formatBeijingDateTime(value),
    },
    {
      title: '处理方式',
      dataIndex: 'operation_type',
      width: 130,
      render: (value: string, record) =>
        value === 'PERSONAL_USE' &&
        (record.remark === '员工签收' || record.change_summary === '签字')
          ? '签字'
          : (lifecycleTypeLabels[value] ?? value),
    },
    {
      title: '处理人',
      dataIndex: 'operator_name',
      width: 130,
      render: (value: string | null | undefined, record) => value || `用户 #${record.operator_id}`,
    },
    {
      title: '处理内容',
      dataIndex: 'change_summary',
      render: (value: string | null | undefined, record) =>
        value || record.remark || '该操作未记录变更明细',
    },
  ]

  if (isLoading) {
    return <RecordsLoading />
  }
  if (isError) {
    return (
      <StatePanel mode="error" message="资产履历加载失败" retryLabel="重新加载" onRetry={onRetry} />
    )
  }
  if (!records?.length) {
    return <StatePanel mode="empty" message="当前资产暂无履历记录" />
  }

  return (
    <SectionPanel title="资产履历" icon={<FileClock aria-hidden="true" size={18} />}>
      <Table<AssetLifecycleRecord>
        className="asset-detail__history-table"
        rowKey="id"
        columns={columns}
        dataSource={records}
        pagination={false}
        scroll={{ x: 860 }}
      />
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

function RepairRecordsTab({ assetId, showAmount }: { assetId: number; showAmount: boolean }) {
  const query = useQuery({
    queryKey: ['assets', 'repair-records', assetId],
    queryFn: () => assetManagementApi.repairRecords(assetId),
  })

  if (query.isLoading) return <RecordsLoading />
  if (query.isError) {
    return (
      <StatePanel
        mode="error"
        message="维修记录加载失败"
        retryLabel="重新加载"
        onRetry={() => void query.refetch()}
      />
    )
  }
  if (!query.data?.length) return <StatePanel mode="empty" message="当前资产暂无维修记录" />

  return (
    <SectionPanel title="维修记录" icon={<Wrench aria-hidden="true" size={18} />}>
      <div className="asset-detail__record-list">
        {query.data.map((record: AssetRepairRecord) => (
          <article key={record.id} className="asset-detail__record-card">
            <header className="asset-detail__record-card-header">
              <div className="asset-detail__record-title">
                <span className="asset-detail__record-icon">
                  <Wrench aria-hidden="true" size={18} />
                </span>
                <div>
                  <strong>{record.completed_at ? '维修完成' : '维修中'}</strong>
                  <small>{record.repair_no}</small>
                </div>
              </div>
              <StatusLabel
                status={record.completed_at ? 'COMPLETED' : 'REPAIRING'}
                label={record.completed_at ? '已完成' : '维修中'}
              />
            </header>
            <div className="asset-detail__record-grid">
              <RecordFact label="故障原因" value={record.fault_description} />
              <RecordFact label="维修前状态" value={assetStatusLabel(record.before_status)} />
              <RecordFact label="维修供应商" value={record.repair_supplier_name} />
              <RecordFact
                label="维修费用"
                value={showAmount ? formatMoneyValue(record.repair_cost ?? null) : '无金额查看权限'}
              />
              <RecordFact label="送修时间" value={formatBeijingDateTime(record.sent_at)} />
              <RecordFact
                label="完成时间"
                value={
                  record.completed_at ? formatBeijingDateTime(record.completed_at) : '尚未完成'
                }
              />
              <RecordFact label="维修结果" value={record.repair_result} />
              <RecordFact
                label="确认人"
                value={record.confirmed_by ? `用户 #${record.confirmed_by}` : '尚未确认'}
              />
            </div>
          </article>
        ))}
      </div>
    </SectionPanel>
  )
}

function ScrapRecordsTab({ assetId, showAmount }: { assetId: number; showAmount: boolean }) {
  const query = useQuery({
    queryKey: ['assets', 'scrap-records', assetId],
    queryFn: () => assetManagementApi.scrapRecords(assetId),
  })

  if (query.isLoading) return <RecordsLoading />
  if (query.isError) {
    return (
      <StatePanel
        mode="error"
        message="报废记录加载失败"
        retryLabel="重新加载"
        onRetry={() => void query.refetch()}
      />
    )
  }
  if (!query.data?.length) return <StatePanel mode="empty" message="当前资产暂无报废记录" />

  return (
    <SectionPanel title="报废记录" icon={<Trash2 aria-hidden="true" size={18} />}>
      <div className="asset-detail__record-list">
        {query.data.map((record: AssetScrapRecord) => (
          <article key={record.id} className="asset-detail__record-card">
            <header className="asset-detail__record-card-header">
              <div className="asset-detail__record-title">
                <span className="asset-detail__record-icon">
                  <Trash2 aria-hidden="true" size={18} />
                </span>
                <div>
                  <strong>资产报废</strong>
                  <small>{record.scrap_no}</small>
                </div>
              </div>
              <StatusLabel status="SCRAPPED" label="已报废" />
            </header>
            <div className="asset-detail__record-grid">
              <RecordFact label="实际处置日期" value={record.disposal_date ?? record.scrap_date} />
              <RecordFact label="报废原因" value={record.reason} />
              <RecordFact label="处置方式" value={scrapDispositionLabel(record.disposition)} />
              <RecordFact label="处置备注" value={record.disposition_remark} />
              <RecordFact
                label="回收金额"
                value={
                  showAmount ? formatMoneyValue(record.scrap_amount ?? null) : '无金额查看权限'
                }
              />
              <RecordFact label="确认时间" value={formatBeijingDateTime(record.confirmed_at)} />
              <RecordFact label="确认人" value={`用户 #${record.confirmed_by}`} />
            </div>
            <footer>记录创建于 {formatBeijingDateTime(record.created_at)}</footer>
          </article>
        ))}
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
              <RecordFact label="截止时间" value={formatBeijingDateTime(record.deadline_at)} />
              <RecordFact label="实物结果" value={inventoryLabel(record.physical_result)} />
              <RecordFact label="地点结果" value={inventoryLabel(record.location_result)} />
              <RecordFact label="账面地点" value={record.ledger_location_name} />
              <RecordFact label="实际地点" value={record.actual_location_text} />
              <RecordFact label="提交人" value={record.submitted_by_name} />
              <RecordFact
                label="提交时间"
                value={record.submitted_at ? formatBeijingDateTime(record.submitted_at) : '—'}
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
                  label={executionStatusLabel(record.execution_status)}
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
                value={record.submitted_at ? formatBeijingDateTime(record.submitted_at) : '—'}
              />
              <RecordFact
                label="审批时间"
                value={record.approved_at ? formatBeijingDateTime(record.approved_at) : '—'}
              />
              <RecordFact
                label="执行时间"
                value={record.executed_at ? formatBeijingDateTime(record.executed_at) : '—'}
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
                          {task.decided_at ? formatBeijingDateTime(task.decided_at) : '等待处理'}
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
  USAGE_SIGN: '领用签收证据',
  RETURN_HANDOVER: '退库交还证据',
  RETURN_INSPECTION: '退库验收证据',
  TRANSFER_RECEIPT: '交接签收证据',
  OTHER: '其他附件',
}

const attachmentTypeOptions = Object.entries(attachmentTypeLabels).map(([value, label]) => ({
  value: value as AssetAttachmentType,
  label,
}))

const attachmentDocumentTypeLabels: Record<AssetAttachmentDocumentType, string> = {
  ASSET_PHOTO: '资产照片',
  CONTRACT: '合同',
  INVOICE: '发票',
  ACCEPTANCE: '验收资料',
  REPAIR_PHOTO: '维修照片',
  REPAIR_QUOTE: '维修报价单',
  REPAIR_INVOICE: '维修发票',
  SCRAP_CERTIFICATE: '报废证明',
  DISPOSAL_VOUCHER: '残值处置凭证',
  SIGN_PHOTO: '签收照片',
  RETURN_PHOTO: '交还照片',
  INSPECTION_PHOTO: '验收照片',
  TRANSFER_RECEIPT_PHOTO: '交接签收照片',
  ELECTRONIC_SIGNATURE: '电子签名',
  OTHER: '其他附件',
}

const documentTypesByBusinessType: Record<AssetAttachmentType, AssetAttachmentDocumentType[]> = {
  PHOTO: ['ASSET_PHOTO'],
  CONTRACT: ['CONTRACT'],
  INVOICE: ['INVOICE'],
  ACCEPTANCE: ['ACCEPTANCE'],
  REPAIR: ['REPAIR_PHOTO', 'REPAIR_QUOTE', 'REPAIR_INVOICE', 'OTHER'],
  SCRAP: ['SCRAP_CERTIFICATE', 'DISPOSAL_VOUCHER', 'OTHER'],
  USAGE_SIGN: ['SIGN_PHOTO', 'ELECTRONIC_SIGNATURE'],
  RETURN_HANDOVER: ['RETURN_PHOTO', 'ELECTRONIC_SIGNATURE'],
  RETURN_INSPECTION: ['INSPECTION_PHOTO', 'ELECTRONIC_SIGNATURE'],
  TRANSFER_RECEIPT: ['TRANSFER_RECEIPT_PHOTO', 'ELECTRONIC_SIGNATURE'],
  OTHER: ['OTHER'],
}

function defaultDocumentType(businessType: AssetAttachmentType): AssetAttachmentDocumentType {
  return documentTypesByBusinessType[businessType][0]
}

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
  const [businessId, setBusinessId] = useState<number | null>(null)
  const [documentType, setDocumentType] = useState<AssetAttachmentDocumentType>('ASSET_PHOTO')
  const [voidTarget, setVoidTarget] = useState<AssetAttachment | null>(null)
  const [voidReason, setVoidReason] = useState('')

  const query = useQuery({
    queryKey: ['assets', 'attachments', assetId],
    queryFn: () => attachmentApi.list(assetId),
  })
  const repairQuery = useQuery({
    queryKey: ['assets', 'repair-records', assetId],
    queryFn: () => assetManagementApi.repairRecords(assetId),
    enabled: canManage && businessType === 'REPAIR',
  })
  const scrapQuery = useQuery({
    queryKey: ['assets', 'scrap-records', assetId],
    queryFn: () => assetManagementApi.scrapRecords(assetId),
    enabled: canManage && businessType === 'SCRAP',
  })
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ['assets', 'attachments', assetId] })
  const uploadMutation = useMutation({
    mutationFn: (file: File) =>
      attachmentApi.upload(assetId, {
        businessType,
        businessId,
        documentType,
        file,
      }),
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
    onError: (error) => void message.error(error instanceof Error ? error.message : '附件下载失败'),
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
  const requiresBusinessRecord = businessType === 'REPAIR' || businessType === 'SCRAP'
  const businessRecordOptions =
    businessType === 'REPAIR'
      ? (repairQuery.data ?? []).map((record) => ({
          value: record.id,
          label: `${record.repair_no} · ${record.fault_description}`,
        }))
      : (scrapQuery.data ?? []).map((record) => ({
          value: record.id,
          label: `${record.scrap_no} · ${record.disposal_date ?? record.scrap_date}`,
        }))
  const documentTypeOptions = documentTypesByBusinessType[businessType].map((value) => ({
    value,
    label: attachmentDocumentTypeLabels[value],
  }))
  const uploadDisabled =
    uploadMutation.isPending ||
    (requiresBusinessRecord && businessId == null) ||
    (businessType === 'REPAIR' && repairQuery.isLoading) ||
    (businessType === 'SCRAP' && scrapQuery.isLoading)

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
                onChange={(value) => {
                  setBusinessType(value)
                  setBusinessId(null)
                  setDocumentType(defaultDocumentType(value))
                }}
                aria-label="附件业务类型"
              />
              {requiresBusinessRecord ? (
                <Select
                  value={businessId}
                  options={businessRecordOptions}
                  loading={businessType === 'REPAIR' ? repairQuery.isLoading : scrapQuery.isLoading}
                  placeholder={businessType === 'REPAIR' ? '选择维修记录' : '选择报废记录'}
                  notFoundContent={businessType === 'REPAIR' ? '暂无维修记录' : '暂无报废记录'}
                  onChange={setBusinessId}
                  aria-label="关联业务记录"
                />
              ) : null}
              <Select
                value={documentType}
                options={documentTypeOptions}
                onChange={setDocumentType}
                aria-label="附件用途"
              />
              <Upload
                accept={businessType === 'PHOTO' ? 'image/jpeg,image/png,image/webp' : undefined}
                showUploadList={false}
                disabled={uploadDisabled}
                beforeUpload={(file) => {
                  uploadMutation.mutate(file)
                  return Upload.LIST_IGNORE
                }}
              >
                <Button
                  type="primary"
                  icon={<UploadCloud aria-hidden="true" size={16} />}
                  loading={uploadMutation.isPending}
                  disabled={uploadDisabled}
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
          <span>报价单、维修发票和残值凭证下载需要金额查看权限</span>
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
                      {attachmentDocumentTypeLabels[attachment.document_type]} ·{' '}
                      {attachmentTypeLabels[attachment.business_type]} ·{' '}
                      {formatFileSize(attachment.size_bytes)}
                    </span>
                    <small>
                      {attachment.business_id ? `关联记录 #${attachment.business_id} · ` : ''}
                      上传于 {formatBeijingDateTime(attachment.created_at)}
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
    value = formatBeijingDateTime(rawValue)
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

function FinancialSummaryTab({
  asset,
  showAmount,
}: {
  asset: AssetDetailRecord
  showAmount: boolean
}) {
  const { i18n } = useTranslation()
  const locale = i18n.resolvedLanguage || 'zh-CN'
  const query = useQuery({
    queryKey: ['assets', 'financial-summary', asset.id],
    queryFn: () => assetManagementApi.financialSummary(asset.id),
    enabled: showAmount,
  })

  if (!showAmount) {
    return <StatePanel mode="empty" message="当前账号无权查看资产金额及折旧信息" />
  }
  if (query.isLoading) {
    return (
      <div className="asset-detail__timeline-loading">
        <Spin />
      </div>
    )
  }
  if (query.isError || !query.data) {
    return (
      <StatePanel
        mode="error"
        message="资产财务折旧信息加载失败"
        retryLabel="重新加载"
        onRetry={() => void query.refetch()}
      />
    )
  }

  const summary = query.data
  const money = (value: string) => formatMoneyValue(value)
  const date = (value: string) => formatAssetDate(value, locale)

  return (
    <div className="asset-detail__groups">
      <SectionPanel
        title="财务折旧摘要"
        icon={<ReceiptText aria-hidden="true" size={18} />}
        extra={<span>查询日期：{date(summary.as_of)}</span>}
      >
        <dl className="asset-detail__fields">
          <div className="asset-detail__field">
            <dt>资产原值</dt>
            <dd>{money(summary.original_amount)}</dd>
          </div>
          <div className="asset-detail__field">
            <dt>残值</dt>
            <dd>{money(summary.residual_value)}</dd>
          </div>
          <div className="asset-detail__field">
            <dt>可折旧金额</dt>
            <dd>{money(summary.depreciable_amount)}</dd>
          </div>
          <div className="asset-detail__field">
            <dt>月折旧额</dt>
            <dd>{money(summary.monthly_depreciation)}</dd>
          </div>
          <div className="asset-detail__field">
            <dt>累计折旧</dt>
            <dd>{money(summary.accumulated_depreciation)}</dd>
          </div>
          <div className="asset-detail__field">
            <dt>资产净值</dt>
            <dd>{money(summary.net_book_value)}</dd>
          </div>
        </dl>
      </SectionPanel>
      <SectionPanel title="折旧口径" icon={<FileClock aria-hidden="true" size={18} />}>
        <dl className="asset-detail__fields">
          <div className="asset-detail__field">
            <dt>折旧方法</dt>
            <dd>{summary.method_name}</dd>
          </div>
          <div className="asset-detail__field">
            <dt>购入日期</dt>
            <dd>{date(summary.purchase_date)}</dd>
          </div>
          <div className="asset-detail__field">
            <dt>预计到期日</dt>
            <dd>{date(summary.expected_expiry_date)}</dd>
          </div>
          <div className="asset-detail__field">
            <dt>使用年限</dt>
            <dd>{summary.service_life_months} 个月</dd>
          </div>
          <div className="asset-detail__field">
            <dt>已折旧月数</dt>
            <dd>{summary.elapsed_months} 个月</dd>
          </div>
          <div className="asset-detail__field">
            <dt>剩余月数</dt>
            <dd>{summary.remaining_months} 个月</dd>
          </div>
        </dl>
        <p className="asset-detail__record-note">
          当前结果为直线法折旧试算，不会修改资产原值，也不会生成会计凭证。
          {summary.is_fully_depreciated ? '该资产已完成预计折旧。' : ''}
        </p>
      </SectionPanel>
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
      ) : tab.key === 'finance' ? (
        <FinancialSummaryTab asset={asset} showAmount={showAmount} />
      ) : tab.key === 'attachments' ? (
        <AttachmentsTab assetId={asset.id} />
      ) : tab.key === 'relations' ? (
        <RelationsTab asset={asset} />
      ) : tab.key === 'history' ? (
        <LifecycleTab {...lifecycleProps} />
      ) : tab.key === 'repairs' ? (
        <RepairRecordsTab assetId={asset.id} showAmount={showAmount} />
      ) : tab.key === 'scrap' ? (
        <ScrapRecordsTab assetId={asset.id} showAmount={showAmount} />
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
  const isScannedCode = assetId === null
  const query = useQuery({
    queryKey: ['assets', 'detail', assetId],
    queryFn: () =>
      assetId === null ? Promise.reject(new Error('INVALID_ASSET_ID')) : getAsset(assetId),
    enabled: assetId !== null,
    retry: false,
  })

  if (isScannedCode) {
    return (
      <Navigate replace to={`/scan-use?asset_code=${encodeURIComponent(assetIdParam ?? '')}`} />
    )
  }
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
