import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Button,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Segmented,
  Select,
  Space,
  Spin,
  Timeline,
  message,
} from 'antd'
import dayjs from 'dayjs'
import {
  Bell,
  Download,
  ArrowLeftRight,
  ArrowUpRight,
  PackageCheck,
  ClipboardPenLine,
  Plus,
  RotateCcw,
  RefreshCw,
  ScanLine,
  Trash2,
  Wrench,
} from 'lucide-react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import BarcodeScanner from '@/components/scanner/BarcodeScanner'
import { assetManagementApi } from '@/api/assetManagement'
import { attachmentApi } from '@/api/attachments'
import {
  assetInformationChangeApi,
  type InformationChangeRequest,
  type InformationChangeType,
  type InformationChangeValue,
} from '@/api/assetInformationChanges'
import {
  assetUsageReturnApi,
  type AssetUsageReturnAction,
  type AssetUsageReturnSubmission,
} from '@/api/assetUsageReturn'
import { listAssets, loadAssetReferences } from '@/api/assets'
import { operationApi, type OperationRequest } from '@/api/operations'
import {
  approvalStatusLabel,
  executionStatusLabel,
  operationTypeLabel as operationTypeCodeLabel,
  workflowHandlerRoleLabel,
  workflowStatusLabel,
} from '@/utils/displayLabels'
import { workbenchApi, type WorkbenchRequestDetail } from '@/api/workbench'
import StatePanel from '@/components/ui/StatePanel'
import type { TreeItem } from '@/api/administration'
import type { AssetSummary } from '@/features/assets/types'
import { useAuthStore } from '@/store/auth'
import type { Tone } from './data'
import EmployeeTaskCenter from './EmployeeTaskCenter'
import ReturnConfirmModal from './ReturnConfirmModal'
import UsageReturnModal from './UsageReturnModal'
import { canHandleInternalDecision, canHandleLocalFeishuDecision } from './workflowActions'
import {
  filterMyAssets,
  filterWorkflowRecords,
  isMyAssetView,
  workflowViewOptions,
  type WorkflowView,
} from './workbenchViews'
import {
  GlassPanel,
  OperationsHero,
  OperationsMetrics,
  SectionHeading,
  StatusPill,
} from './OperationsUI'

type LifecycleAction = 'TRANSFER' | 'REPAIR_START' | 'REPAIR_COMPLETE' | 'SCRAP'

interface Option {
  label: string
  value: number
}

interface LifecycleFormValues {
  asset_ids: number[]
  location_id?: number
  manager_id?: number
  holder_user_id?: number
  vendor?: string
  estimated_cost?: number
  actual_cost?: number
  scrap_details?: Record<
    string,
    {
      disposal_date?: dayjs.Dayjs
      scrap_amount?: number
      disposition?: string
      disposition_remark?: string
    }
  >
  child_action?: 'BLOCK' | 'DETACH' | 'SCRAP'
  reason: string
}

interface InformationChangeFormValues {
  change_type: InformationChangeType
  asset_ids: number[]
  asset_name?: string
  location_id?: number
  manager_id?: number
  original_amount?: number
  zero_amount_reason?: string
  purchase_date?: dayjs.Dayjs
  service_life_months?: number
  warranty_supplier_id?: number
  warranty_contact?: string
  warranty_phone?: string
  warranty_expiry_date?: dayjs.Dayjs
  warranty_description?: string
  reason: string
}

const informationChangeTypeLabels: Record<InformationChangeType, string> = {
  PHYSICAL: '实物信息变更',
  FINANCIAL: '财务信息变更',
  WARRANTY: '维保信息变更',
}

const informationChangeFieldLabels: Record<string, string> = {
  asset_name: '资产名称',
  category_id: '资产分类',
  unit_id: '计量单位',
  supplier_id: '供应商',
  location_id: '存放地点',
  manager_id: '责任管理员',
  source_id: '资产来源',
  specification_model: '规格型号',
  serial_number: '设备序列号',
  receipt_no: '凭证号',
  rfid_tag: 'RFID 标签',
  remark: '备注',
  organization_id: '所属组织',
  original_amount: '金额',
  zero_amount_reason: '零金额原因',
  purchase_date: '购入日期',
  service_life_months: '使用期限（月）',
  warranty_supplier_id: '维保供应商',
  warranty_contact: '维保联系人',
  warranty_phone: '维保电话',
  warranty_expiry_date: '维保到期日',
  warranty_description: '维保说明',
}

const informationChangeOperationTypes = new Set([
  'PHYSICAL_INFO_CHANGE',
  'FINANCIAL_INFO_CHANGE',
  'WARRANTY_INFO_CHANGE',
])

function formatInformationChangeValue(value: InformationChangeValue | undefined): string {
  if (value === undefined) return '未提供'
  if (value === null || value === '') return '空'
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value)
}

const actionMeta: Record<LifecycleAction, { title: string; submit: string; tone: Tone }> = {
  TRANSFER: { title: '发起资产转移', submit: '确认转移', tone: 'violet' },
  REPAIR_START: { title: '登记送修', submit: '开始维修', tone: 'amber' },
  REPAIR_COMPLETE: { title: '完成维修', submit: '确认完成', tone: 'green' },
  SCRAP: { title: '执行资产报废', submit: '确认报废', tone: 'red' },
}

const flowTypes = [
  {
    name: '资产入库',
    description: '登记采购信息并提交审批，审批完成后生成正式资产',
    icon: Plus,
    operationTypes: ['STOCK_IN'],
    tone: 'green' as const,
    action: 'STOCK_IN' as const,
  },
  {
    name: '资产领退',
    description: '个人领用由管理员审批发放、员工签收；退库完成个人验收',
    icon: PackageCheck,
    operationTypes: ['PERSONAL_USE', 'PUBLIC_USE', 'PERSONAL_RETURN', 'PUBLIC_RETURN'],
    tone: 'blue' as const,
    action: null,
  },
  {
    name: '资产转移',
    description: '调整使用人、责任管理员或存放地点，主资产会联动附属资产',
    icon: ArrowLeftRight,
    operationTypes: ['TRANSFER'],
    tone: 'violet' as const,
    action: 'TRANSFER' as const,
  },
  {
    name: '维修处理',
    description: '登记送修和维修完成结果，费用与状态写入永久履历',
    icon: Wrench,
    operationTypes: ['REPAIR_START', 'REPAIR_COMPLETE'],
    tone: 'amber' as const,
    action: 'REPAIR_START' as const,
  },
  {
    name: '资产报废',
    description: '记录报废日期、回收金额，并处理主资产下的附属资产',
    icon: Trash2,
    operationTypes: ['SCRAP'],
    tone: 'red' as const,
    action: 'SCRAP' as const,
  },
  {
    name: '信息变更',
    description: '独立发起实物、财务或维保信息变更，保留前后值与审批履历',
    icon: ClipboardPenLine,
    operationTypes: ['PHYSICAL_INFO_CHANGE', 'FINANCIAL_INFO_CHANGE', 'WARRANTY_INFO_CHANGE'],
    tone: 'cyan' as const,
    action: 'INFO_CHANGE' as const,
  },
]

function operationStatus(record: OperationRequest): { label: string; tone: Tone } {
  if (record.approval_status === 'REJECTED') return { label: '已拒绝', tone: 'red' }
  if (record.approval_status === 'WITHDRAWN') return { label: '已撤回', tone: 'slate' }
  if (record.approval_status === 'PENDING' && record.fulfillment_status === 'PENDING_ISSUE')
    return { label: '待管理员审批发放', tone: 'blue' }
  if (record.fulfillment_status === 'PENDING_ISSUE') return { label: '待管理员发放', tone: 'cyan' }
  if (record.approval_status === 'PENDING') return { label: '待审批', tone: 'blue' }
  if (record.fulfillment_status === 'PENDING_SIGN') return { label: '待员工签收', tone: 'amber' }
  if (record.fulfillment_status === 'SIGN_REFUSED') return { label: '员工拒绝签收', tone: 'red' }
  if (record.return_stage === 'PENDING_INSPECTION') return { label: '待验收退库', tone: 'cyan' }
  if (record.execution_status === 'FAILED') return { label: '执行失败', tone: 'red' }
  if (record.execution_status === 'PROCESSING') return { label: '执行中', tone: 'amber' }
  if (record.execution_status === 'SUCCESS') return { label: '已完成', tone: 'green' }
  if (record.execution_status === 'TERMINATED') return { label: '已终止', tone: 'slate' }
  return { label: '待执行', tone: 'cyan' }
}

function operationTypeDisplayLabel(record: OperationRequest): string {
  if (record.usage_mode === 'BORROW') {
    return record.operation_type === 'PUBLIC_USE' ? '公共借用' : '个人借用'
  }
  return operationTypeCodeLabel(record.operation_type)
}

function operationAssetLabel(record: OperationRequest): string {
  if (record.requested_category) {
    const quantity = record.requested_quantity ? ` × ${record.requested_quantity} 件` : ''
    return `申请 ${record.requested_category.name}${quantity}`
  }
  const first = record.assets[0]
  if (!first) return '未关联资产'
  const extra = record.assets.length > 1 ? ` 等 ${record.assets.length} 件` : ''
  return first.asset_code
    ? `${first.asset_name} · ${first.asset_code}${extra}`
    : `${first.asset_name}${extra}`
}

function actionAllowed(asset: AssetSummary, action: LifecycleAction): boolean {
  if (action === 'REPAIR_COMPLETE') return asset.status === 'REPAIRING'
  if (action === 'REPAIR_START' || action === 'TRANSFER') {
    return asset.status === 'IDLE' || asset.status === 'IN_USE'
  }
  return asset.status !== 'SCRAPPED'
}

interface InformationChangeUser {
  id: number
  name: string
}

function InformationChangeDetailModal({
  open,
  detail,
  loading,
  error,
  currentUserId,
  users,
  onRetry,
  onClose,
}: {
  open: boolean
  detail?: InformationChangeRequest
  loading: boolean
  error: boolean
  currentUserId?: number
  users: InformationChangeUser[]
  onRetry: () => void
  onClose: () => void
}) {
  const userLabel = (userId: number) => {
    if (userId === currentUserId) return '我'
    return users.find((user) => user.id === userId)?.name ?? `用户 #${userId}`
  }
  const approverIds = detail
    ? Array.from(
        new Set(
          detail.approval_timeline.flatMap((step) => step.tasks.map((task) => task.approver_id)),
        ),
      )
    : []

  return (
    <Modal
      open={open}
      title={
        detail
          ? `${informationChangeTypeLabels[detail.change_type]} · ${detail.request_no}`
          : '信息变更详情'
      }
      className="operations-glass-modal"
      width={820}
      footer={null}
      onCancel={onClose}
    >
      {loading ? (
        <div className="operations-loading">
          <Spin />
        </div>
      ) : error ? (
        <StatePanel
          mode="error"
          message="信息变更详情加载失败"
          retryLabel="重新加载"
          onRetry={onRetry}
        />
      ) : detail ? (
        <div className="operations-information-change-detail">
          <div className="operations-information-change-summary">
            <div>
              <span>变更原因</span>
              <strong>{detail.reason}</strong>
            </div>
            <div>
              <span>申请人</span>
              <strong>{userLabel(detail.applicant_id)}</strong>
            </div>
            <div>
              <span>审批人</span>
              <strong>
                {approverIds.length
                  ? approverIds.map((approverId) => userLabel(approverId)).join('、')
                  : detail.requires_feishu_approval
                    ? '飞书审批人'
                    : '暂无审批人'}
              </strong>
            </div>
            <div>
              <span>审批 / 执行状态</span>
              <strong>
                {approvalStatusLabel(detail.approval_status)} /{' '}
                {executionStatusLabel(detail.execution_status)}
              </strong>
            </div>
            <div>
              <span>需要飞书审批</span>
              <strong>{detail.requires_feishu_approval ? '是' : '否'}</strong>
            </div>
            <div>
              <span>执行时间</span>
              <strong>
                {detail.executed_at
                  ? dayjs(detail.executed_at).format('YYYY-MM-DD HH:mm:ss')
                  : '尚未执行'}
              </strong>
            </div>
          </div>
          {detail.external_instance_id ? (
            <p className="operations-modal-note">飞书审批实例：{detail.external_instance_id}</p>
          ) : null}
          <div className="operations-information-change-assets">
            {detail.assets.map((asset) => {
              const fields = Array.from(
                new Set([...Object.keys(asset.before_data), ...Object.keys(asset.target_data)]),
              ).filter((field) => field !== 'version')
              return (
                <article key={asset.asset_id} className="operations-information-change-asset">
                  <div className="operations-information-change-asset__heading">
                    <strong>{asset.asset_name}</strong>
                    <span>{asset.asset_code ?? `资产 #${asset.asset_id}`}</span>
                  </div>
                  <div className="operations-information-change-values">
                    <div className="operations-information-change-values__header">
                      <span>字段</span>
                      <span>变更前值</span>
                      <span>变更后值</span>
                    </div>
                    {fields.map((field) => (
                      <div key={field} className="operations-information-change-values__row">
                        <strong>{informationChangeFieldLabels[field] ?? field}</strong>
                        <span>{formatInformationChangeValue(asset.before_data[field])}</span>
                        <span>{formatInformationChangeValue(asset.target_data[field])}</span>
                      </div>
                    ))}
                  </div>
                </article>
              )
            })}
          </div>
          <p className="operations-modal-note">
            变更执行完成后，会以同一申请单号写入资产履历；变更前值和变更后值作为不可变快照保留。
          </p>
        </div>
      ) : null}
    </Modal>
  )
}

function WorkflowTimeline({
  detail,
  onDownload,
}: {
  detail: WorkbenchRequestDetail
  onDownload: (attachmentId: number, filename: string) => Promise<void>
}) {
  return (
    <div className="employee-task-center__detail">
      <div className="employee-task-center__next-step">
        <span>当前状态：{workflowStatusLabel(detail.display_status)}</span>
        <strong>下一步：{detail.next_step}</strong>
        <small>
          当前等待：
          {detail.current_handler?.users
            .map((item) => item?.name)
            .filter(Boolean)
            .join('、') ||
            (detail.current_handler?.role
              ? workflowHandlerRoleLabel(detail.current_handler.role)
              : '无人处理')}
        </small>
      </div>
      <Timeline
        items={detail.timeline.map((event) => ({
          color:
            event.status === 'REJECTED' ? 'red' : event.status === 'CURRENT' ? 'blue' : 'green',
          children: (
            <div className="employee-task-center__timeline-event">
              <strong>{event.title}</strong>
              <span>
                {event.occurred_at
                  ? dayjs(event.occurred_at).format('YYYY-MM-DD HH:mm:ss')
                  : '等待处理'}
              </span>
              <small>操作人：{event.actor?.name ?? '系统 / 待处理'}</small>
              {event.asset_codes.length ? (
                <small>资产编码：{event.asset_codes.join('、')}</small>
              ) : null}
              {event.remark ? <small>备注：{event.remark}</small> : null}
              {event.approval_result ? (
                <small>
                  审批结果：{event.approval_result === 'APPROVE' ? '通过' : event.approval_result}
                </small>
              ) : null}
              {event.rejection_reason ? <small>拒绝原因：{event.rejection_reason}</small> : null}
              {event.attachments.length ? (
                <Space wrap size={[4, 4]}>
                  <small>履约证据：</small>
                  {event.attachments.map((attachment) => (
                    <Button
                      key={attachment.id}
                      type="link"
                      size="small"
                      icon={<Download size={12} />}
                      onClick={() => void onDownload(attachment.id, attachment.original_name)}
                    >
                      {attachment.original_name}
                    </Button>
                  ))}
                </Space>
              ) : null}
            </div>
          ),
        }))}
      />
    </div>
  )
}

export default function Workflows() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [filter, setFilter] = useState<WorkflowView>('ALL')
  const [action, setAction] = useState<LifecycleAction | null>(null)
  const [usageReturnOpen, setUsageReturnOpen] = useState(false)
  const [usageReturnInitialAction, setUsageReturnInitialAction] = useState<
    AssetUsageReturnAction | undefined
  >(undefined)
  const [scanOpen, setScanOpen] = useState(false)
  const [workflowScanOpen, setWorkflowScanOpen] = useState(false)
  const [managerModalAssets, setManagerModalAssets] = useState<AssetSummary[]>([])
  const [employeeReturnAssetIds, setEmployeeReturnAssetIds] = useState<number[]>([])
  const [informationChangeOpen, setInformationChangeOpen] = useState(false)
  const [informationChangeDetailId, setInformationChangeDetailId] = useState<number | null>(null)
  const [workflowDetailId, setWorkflowDetailId] = useState<number | null>(null)
  const [returnConfirmTarget, setReturnConfirmTarget] = useState<OperationRequest | null>(null)
  const [issueTarget, setIssueTarget] = useState<OperationRequest | null>(null)
  const [selectedIssueAssetIds, setSelectedIssueAssetIds] = useState<number[]>([])
  const [issueRemark, setIssueRemark] = useState('管理员已核对并发放资产')
  const [issueRegionId, setIssueRegionId] = useState<number>()
  const [issueLocationId, setIssueLocationId] = useState<number>()
  const [remindTarget, setRemindTarget] = useState<OperationRequest | null>(null)
  const [remindReason, setRemindReason] = useState('')
  const [withdrawTarget, setWithdrawTarget] = useState<OperationRequest | null>(null)
  const [withdrawReason, setWithdrawReason] = useState('')
  const [returnRequestTarget, setReturnRequestTarget] = useState<OperationRequest | null>(null)
  const [returnRequestReason, setReturnRequestReason] = useState('')
  const [extensionReviewTarget, setExtensionReviewTarget] = useState<
    import('@/api/assetUsageReturn').BorrowExtensionRequest | null
  >(null)
  const [form] = Form.useForm<LifecycleFormValues>()
  const [informationChangeForm] = Form.useForm<InformationChangeFormValues>()
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const currentUserId = useAuthStore((state) => state.user?.id)
  const permissions = useAuthStore((state) => state.user?.permissions)
  const canManageUsage = permissions?.includes('asset:usage:manage') ?? false
  const canSelfUsage = permissions?.includes('asset:usage:self') ?? false
  const canSelfReturn = permissions?.includes('asset:return:self') ?? false
  const canViewAssets = permissions?.includes('asset:view') ?? false
  useEffect(() => {
    const requestId = searchParams.get('request')
    if (!requestId) return
    const parsedId = Number(requestId)
    if (Number.isInteger(parsedId) && parsedId > 0) setWorkflowDetailId(parsedId)
    setSearchParams(
      (params) => {
        params.delete('request')
        return params
      },
      { replace: true },
    )
  }, [searchParams, setSearchParams])
  const employeeTaskCenter = !canManageUsage && (canSelfUsage || canSelfReturn)
  const locationState = location.state as {
    openUsageReturn?: boolean
    usageReturnAction?: AssetUsageReturnAction
  } | null
  const availableUsageReturnActions = useMemo<AssetUsageReturnAction[]>(() => {
    const actions: AssetUsageReturnAction[] = []
    if (canManageUsage)
      actions.push(
        'PERSONAL_USE',
        'PUBLIC_USE',
        'PERSONAL_BORROW',
        'PUBLIC_BORROW',
        'PERSONAL_RETURN',
        'PUBLIC_RETURN',
      )
    else if (canSelfUsage)
      actions.push('PERSONAL_USE', 'PERSONAL_BORROW', 'PUBLIC_USE', 'PUBLIC_BORROW')
    if (canSelfReturn) actions.push('PERSONAL_RETURN')
    return actions
  }, [canManageUsage, canSelfReturn, canSelfUsage])
  useEffect(() => {
    if (!locationState?.openUsageReturn) return
    const initialAction =
      locationState.usageReturnAction &&
      availableUsageReturnActions.includes(locationState.usageReturnAction)
        ? locationState.usageReturnAction
        : undefined
    setUsageReturnInitialAction(initialAction)
    setEmployeeReturnAssetIds([])
    setUsageReturnOpen(true)
    navigate(location.pathname, { replace: true, state: null })
  }, [
    availableUsageReturnActions,
    location.pathname,
    locationState?.openUsageReturn,
    locationState?.usageReturnAction,
    navigate,
  ])
  const openWorkflowScan = () => {
    if (!availableUsageReturnActions.length) {
      void message.warning('当前账号没有发起领用或借用的权限')
      return
    }
    setWorkflowScanOpen(true)
  }
  const query = useQuery({
    queryKey: ['operation-requests'],
    queryFn: () => operationApi.list(0, 50),
    enabled: !employeeTaskCenter,
  })
  const workflowDetailQuery = useQuery({
    queryKey: ['workbench', 'detail', workflowDetailId],
    queryFn: () => {
      if (workflowDetailId === null) throw new Error('未选择业务单')
      return workbenchApi.detail(workflowDetailId)
    },
    enabled: workflowDetailId !== null,
  })
  const downloadWorkflowEvidence = async (attachmentId: number, filename: string) => {
    try {
      const blob = await attachmentApi.download(attachmentId)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      link.click()
      URL.revokeObjectURL(url)
    } catch (error: unknown) {
      void message.error(error instanceof Error ? error.message : '履约证据下载失败')
    }
  }
  const informationChangeDetailQuery = useQuery({
    queryKey: ['asset-information-change-request', informationChangeDetailId],
    queryFn: () => {
      if (informationChangeDetailId === null) throw new Error('未选择信息变更单')
      return assetInformationChangeApi.detail(informationChangeDetailId)
    },
    enabled: informationChangeDetailId !== null,
  })
  const assetQuery = useQuery({
    queryKey: ['assets', 'workflow-picker'],
    queryFn: () => listAssets({ page: 1, size: 100 }),
    enabled: canViewAssets,
  })

  const referenceQuery = useQuery({
    queryKey: ['asset-form', 'references'],
    queryFn: loadAssetReferences,
    enabled: canManageUsage,
    staleTime: 60_000,
  })
  const selfReferenceQuery = useQuery({
    queryKey: ['asset-usage', 'self-service-references'],
    queryFn: assetUsageReturnApi.selfServiceReferences,
    enabled: canSelfUsage,
    staleTime: 30_000,
  })
  const myAssetsQuery = useQuery({
    queryKey: ['asset-usage', 'my-assets'],
    queryFn: assetUsageReturnApi.myAssets,
    enabled: canSelfUsage || canSelfReturn,
  })
  const publicObjectQuery = useQuery({
    queryKey: ['public-usage-objects', 'enabled'],
    queryFn: () => assetManagementApi.publicObjects(false),
    enabled: canManageUsage || canSelfUsage,
    staleTime: 60_000,
  })
  const pendingTransferHandoversQuery = useQuery({
    queryKey: ['transfer-handovers', 'pending'],
    queryFn: assetManagementApi.pendingTransferHandovers,
    enabled: canManageUsage,
  })

  const pendingExtensionsQuery = useQuery({
    queryKey: ['borrow-extensions', 'pending'],
    queryFn: assetUsageReturnApi.pendingBorrowExtensions,
    enabled: canManageUsage,
  })
  const issueCandidatesQuery = useQuery({
    queryKey: ['asset-usage', 'issue-candidates', issueTarget?.id],
    queryFn: () => {
      if (!issueTarget) throw new Error('未选择待发放申请')
      return assetUsageReturnApi.issueCandidates(issueTarget.id)
    },
    enabled: issueTarget !== null,
  })
  const records = useMemo(() => query.data?.items ?? [], [query.data])
  const assets = useMemo(() => assetQuery.data?.records ?? [], [assetQuery.data])
  const myApprovalTasksQuery = useQuery({
    queryKey: ['approval-tasks', 'workflows'],
    queryFn: operationApi.myTasks,
    enabled: canManageUsage,
  })
  const pendingApprovalTasks = useMemo(
    () => myApprovalTasksQuery.data?.filter((task) => task.status === 'PENDING') ?? [],
    [myApprovalTasksQuery.data],
  )
  const pendingApprovalTaskByOperationId = useMemo(
    () => new Map(pendingApprovalTasks.map((task) => [task.operation_request_id, task])),
    [pendingApprovalTasks],
  )
  const filteredRecords = useMemo(
    () =>
      filterWorkflowRecords(
        records,
        filter,
        currentUserId,
        (record) => operationStatus(record).label,
      ),
    [currentUserId, filter, records],
  )
  const filteredMyAssets = useMemo(
    () => filterMyAssets(myAssetsQuery.data ?? [], filter),
    [filter, myAssetsQuery.data],
  )
  const showingMyAssets = isMyAssetView(filter)

  const pendingApproval = records.filter((record) => record.approval_status === 'PENDING').length
  const processing = records.filter((record) => record.execution_status === 'PROCESSING').length
  const completed = records.filter((record) => record.execution_status === 'SUCCESS').length
  const failed = records.filter((record) => record.execution_status === 'FAILED').length

  const transferHandoverMutation = useMutation({
    mutationFn: ({ id }: { id: number; action: 'OUTGOING' }) =>
      assetManagementApi.confirmTransferOutgoing(id, '管理员已确认资产转出'),
    onSuccess: async () => {
      await message.success('已确认转出，等待接收员工签收')
      await queryClient.invalidateQueries({ queryKey: ['transfer-handovers'] })
      await queryClient.invalidateQueries({ queryKey: ['workbench'] })
    },
    onError: (error: Error) => void message.error(error.message),
  })

  const syncFeishuApprovalsMutation = useMutation({
    mutationFn: () => operationApi.syncFeishuApprovals(),
    onSuccess: async (result) => {
      await message.success(
        result.synced ? `已同步 ${result.synced} 条飞书审批结果` : '飞书审批结果已是最新',
      )
      await queryClient.invalidateQueries({ queryKey: ['operation-requests'] })
    },
    onError: (error: Error) => void message.error(error.message),
  })
  const extensionReviewMutation = useMutation({
    mutationFn: ({
      extensionId,
      approved,
      opinion,
    }: {
      extensionId: number
      approved: boolean
      opinion: string
    }) =>
      approved
        ? assetUsageReturnApi.approveBorrowExtension(extensionId, opinion)
        : assetUsageReturnApi.rejectBorrowExtension(extensionId, opinion),
    onSuccess: async (_result, variables) => {
      setExtensionReviewTarget(null)
      await message.success(variables.approved ? '借用延期已批准' : '借用延期已拒绝')
      await queryClient.invalidateQueries({ queryKey: ['borrow-extensions'] })
      await queryClient.invalidateQueries({ queryKey: ['workbench'] })
      await queryClient.invalidateQueries({ queryKey: ['operation-requests'] })
    },
    onError: (error: Error) => void message.error(error.message),
  })

  const withdrawMutation = useMutation({
    mutationFn: ({ operationId, reason }: { operationId: number; reason: string }) =>
      operationApi.withdraw(operationId, reason, crypto.randomUUID()),
    onSuccess: async (result) => {
      setWithdrawTarget(null)
      setWithdrawReason('')
      await message.success(`申请 ${result.request_no} 已撤回，资产已解除占用`)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['operation-requests'] }),
        queryClient.invalidateQueries({ queryKey: ['approval-tasks'] }),
        queryClient.invalidateQueries({ queryKey: ['assets'] }),
        queryClient.invalidateQueries({ queryKey: ['asset-usage', 'my-assets'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['todo-center'] }),
        queryClient.invalidateQueries({ queryKey: ['workbench'] }),
      ])
    },
    onError: (error: Error) => void message.error(error.message),
  })

  const reminderMutation = useMutation({
    mutationFn: ({ operationId, reason }: { operationId: number; reason: string }) =>
      operationApi.remind(operationId, reason),
    onSuccess: async (result) => {
      setRemindTarget(null)
      setRemindReason('')
      void message.success(
        `已生成系统内催办记录，下次可催办时间 ${dayjs(result.next_allowed_at).format('HH:mm')}`,
      )
      await queryClient.invalidateQueries({ queryKey: ['operation-requests'] })
    },
    onError: (error: Error) => void message.error(error.message),
  })

  const usageReturnMutation = useMutation({
    mutationFn: (submission: AssetUsageReturnSubmission) => assetUsageReturnApi.submit(submission),
    onSuccess: async (result) => {
      const isEmployeeSelfUse =
        result.applicant_id === currentUserId && result.operation_type === 'PERSONAL_USE'
      setUsageReturnOpen(false)
      setUsageReturnInitialAction(undefined)
      setEmployeeReturnAssetIds([])
      if (isEmployeeSelfUse) {
        setSearchParams(
          (params) => {
            params.set('request', String(result.id))
            return params
          },
          { replace: true },
        )
      } else {
        const statusText = result.execution_status === 'SUCCESS' ? '已完成办理' : '已提交真实申请'
        await message.success(`${statusText}，单号 ${result.request_no}`)
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['operation-requests'] }),
        queryClient.invalidateQueries({ queryKey: ['assets'] }),
        queryClient.invalidateQueries({ queryKey: ['asset-usage', 'my-assets'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['todo-center'] }),
        queryClient.invalidateQueries({ queryKey: ['workbench'] }),
      ])
    },
    onError: (error: Error) => void message.error(error.message),
  })

  const fulfillmentMutation = useMutation({
    mutationFn: ({
      operationId,
      action,
      remark,
      assetIds,
      regionId,
      locationId,
    }: {
      operationId: number
      action: 'ISSUE' | 'SIGN' | 'REFUSE_SIGN'
      remark?: string
      assetIds?: number[]
      regionId?: number
      locationId?: number
    }) => {
      if (action === 'ISSUE')
        return assetUsageReturnApi.issue(operationId, {
          asset_ids: assetIds ?? [],
          region_id: regionId ?? 0,
          location_id: locationId ?? 0,
          remark,
        })
      if (action === 'SIGN') return assetUsageReturnApi.sign(operationId, remark)
      return assetUsageReturnApi.refuseSign(operationId, remark ?? '员工拒绝签收')
    },
    onSuccess: async (_result, variables) => {
      if (variables.action === 'ISSUE') {
        setIssueTarget(null)
        setSelectedIssueAssetIds([])
        setIssueRegionId(undefined)
        setIssueLocationId(undefined)
      }
      const text =
        variables.action === 'ISSUE'
          ? '审批已通过，资产已发放，等待员工签收'
          : variables.action === 'SIGN'
            ? '已完成员工签收，资产已转为在用'
            : '已拒绝签收，管理员可重新发放'
      await message.success(text)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['operation-requests'] }),
        queryClient.invalidateQueries({ queryKey: ['assets'] }),
        queryClient.invalidateQueries({ queryKey: ['asset-usage', 'my-assets'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['todo-center'] }),
        queryClient.invalidateQueries({ queryKey: ['asset-usage', 'issue-candidates'] }),
        queryClient.invalidateQueries({ queryKey: ['workbench'] }),
      ])
    },
    onError: (error: Error) => void message.error(error.message),
  })

  const localFeishuActionMutation = useMutation({
    mutationFn: ({
      operationId,
      operationType,
      action,
      reason,
    }: {
      operationId: number
      operationType: string
      action: 'APPROVE' | 'REJECT'
      reason?: string
    }) => assetUsageReturnApi.mockFeishuAction(operationId, operationType, action, reason),
    onSuccess: async (_result, variables) => {
      await message.success(variables.action === 'APPROVE' ? '模拟审批已通过' : '模拟审批已拒绝')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['operation-requests'] }),
        queryClient.invalidateQueries({ queryKey: ['assets'] }),
        queryClient.invalidateQueries({ queryKey: ['asset-usage', 'my-assets'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['todo-center'] }),
      ])
    },
    onError: (error: Error) => void message.error(error.message),
  })

  const internalApprovalMutation = useMutation({
    mutationFn: ({
      taskId,
      action,
      opinion,
    }: {
      taskId: number
      action: 'APPROVE' | 'REJECT'
      opinion: string
    }) =>
      action === 'APPROVE'
        ? operationApi.approve(taskId, opinion)
        : operationApi.reject(taskId, opinion),
    onSuccess: async (_result, variables) => {
      await message.success(variables.action === 'APPROVE' ? '审批已通过' : '审批已拒绝')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['operation-requests'] }),
        queryClient.invalidateQueries({ queryKey: ['approval-tasks'] }),
        queryClient.invalidateQueries({ queryKey: ['assets'] }),
        queryClient.invalidateQueries({ queryKey: ['asset-usage', 'my-assets'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['todo-center'] }),
        queryClient.invalidateQueries({ queryKey: ['workbench'] }),
      ])
    },
    onError: (error: Error) => void message.error(error.message),
  })

  const borrowReturnRequestMutation = useMutation({
    mutationFn: ({ operationId, reason }: { operationId: number; reason: string }) =>
      assetUsageReturnApi.requestBorrowReturn(operationId, reason),
    onSuccess: async (result) => {
      setReturnRequestTarget(null)
      setReturnRequestReason('')
      await message.success(`已要求员工归还借用资产，单号 ${result.request_no}`)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['operation-requests'] }),
        queryClient.invalidateQueries({ queryKey: ['workbench'] }),
      ])
    },
    onError: (error: Error) => void message.error(error.message),
  })

  const returnConfirmMutation = useMutation({
    mutationFn: ({
      operationId,
      payload,
    }: {
      operationId: number
      payload: Parameters<typeof assetUsageReturnApi.confirmPersonalReturn>[1]
    }) => assetUsageReturnApi.confirmPersonalReturn(operationId, payload),
    onSuccess: async (result) => {
      setReturnConfirmTarget(null)
      await message.success(`退库验收已完成，单号 ${result.request_no}`)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['operation-requests'] }),
        queryClient.invalidateQueries({ queryKey: ['assets'] }),
        queryClient.invalidateQueries({ queryKey: ['asset-usage', 'my-assets'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['todo-center'] }),
      ])
    },
    onError: (error: Error) => void message.error(error.message),
  })

  const informationChangeMutation = useMutation({
    mutationFn: (values: InformationChangeFormValues) => {
      const selected = assets.filter((asset) => values.asset_ids.includes(asset.id))
      if (selected.length !== values.asset_ids.length)
        throw new Error('所选资产已失效，请刷新后重试')
      const changes: Record<string, string | number | null> = {}
      if (values.change_type === 'PHYSICAL') {
        if (values.asset_name?.trim()) changes.asset_name = values.asset_name.trim()
        if (values.location_id !== undefined) changes.location_id = values.location_id
        if (values.manager_id !== undefined) changes.manager_id = values.manager_id
      } else if (values.change_type === 'FINANCIAL') {
        if (values.original_amount !== undefined)
          changes.original_amount = values.original_amount.toFixed(2)
        if (values.zero_amount_reason !== undefined)
          changes.zero_amount_reason = values.zero_amount_reason.trim() || null
        if (values.purchase_date) changes.purchase_date = values.purchase_date.format('YYYY-MM-DD')
        if (values.service_life_months !== undefined)
          changes.service_life_months = values.service_life_months
      } else {
        if (values.warranty_supplier_id !== undefined)
          changes.warranty_supplier_id = values.warranty_supplier_id
        if (values.warranty_contact !== undefined)
          changes.warranty_contact = values.warranty_contact.trim() || null
        if (values.warranty_phone !== undefined)
          changes.warranty_phone = values.warranty_phone.trim() || null
        if (values.warranty_expiry_date)
          changes.warranty_expiry_date = values.warranty_expiry_date.format('YYYY-MM-DD')
        if (values.warranty_description !== undefined)
          changes.warranty_description = values.warranty_description.trim() || null
      }
      if (!Object.keys(changes).length) throw new Error('请至少填写一个变更后的字段')
      return assetInformationChangeApi.submit({
        change_type: values.change_type,
        items: selected.map((asset) => ({ asset_id: asset.id, version: asset.version, changes })),
        reason: values.reason,
      })
    },
    onSuccess: async (result) => {
      setInformationChangeOpen(false)
      informationChangeForm.resetFields()
      await message.success(`信息变更单 ${result.request_no} 已提交审批`)
      await queryClient.invalidateQueries({ queryKey: ['operation-requests'] })
    },
    onError: (error: Error) => void message.error(error.message),
  })

  const mutation = useMutation({
    mutationFn: async (values: LifecycleFormValues) => {
      if (!action) throw new Error('请选择业务类型')
      const selected = assets.filter((asset) => values.asset_ids.includes(asset.id))
      if (selected.length !== values.asset_ids.length)
        throw new Error('所选资产已失效，请刷新后重试')
      const items = selected.map((asset) => ({ asset_id: asset.id, version: asset.version }))
      if (action === 'TRANSFER') {
        if (values.holder_user_id !== undefined) {
          return assetManagementApi.transferHandover({
            items,
            receiver_user_id: values.holder_user_id,
            location_id: values.location_id,
            manager_id: values.manager_id,
            reason: values.reason,
          })
        }
        return assetManagementApi.transfer({
          items,
          location_id: values.location_id,
          manager_id: values.manager_id,
          holder_user_id: values.holder_user_id,
          reason: values.reason,
        })
      }
      if (action === 'REPAIR_START') {
        return assetManagementApi.repairStart({
          items,
          vendor: values.vendor?.trim() || undefined,
          estimated_cost:
            values.estimated_cost === undefined ? undefined : values.estimated_cost.toFixed(2),
          reason: values.reason,
        })
      }
      if (action === 'REPAIR_COMPLETE') {
        return assetManagementApi.repairComplete({
          items,
          actual_cost: values.actual_cost === undefined ? undefined : values.actual_cost.toFixed(2),
          result: values.reason,
        })
      }
      const scrapDetails = values.scrap_details ?? {}
      return assetManagementApi.scrap({
        items: items.map((item) => {
          const detail = scrapDetails[String(item.asset_id)]
          if (detail?.scrap_amount === undefined) throw new Error('请逐件填写报废回收金额')
          return {
            ...item,
            scrap_amount: detail.scrap_amount.toFixed(2),
            disposition: detail.disposition?.trim() || undefined,
            disposition_remark: detail.disposition_remark?.trim() || undefined,
            disposal_date: (detail.disposal_date ?? dayjs()).format('YYYY-MM-DD'),
          }
        }),
        child_action: values.child_action ?? 'BLOCK',
        reason: values.reason,
      })
    },
    onSuccess: async (result) => {
      await message.success(`已处理 ${result.updated_count} 件资产，命令号 ${result.command_no}`)
      setAction(null)
      form.resetFields()
      void queryClient.invalidateQueries({ queryKey: ['assets'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error: Error) => void message.error(error.message),
  })

  const openAction = (next: LifecycleAction) => {
    setAction(next)
    form.resetFields()
    form.setFieldsValue({
      asset_ids: [],
      scrap_details: {},
      child_action: 'BLOCK',
      reason: '',
    })
  }

  const selectableAssets = action ? assets.filter((asset) => actionAllowed(asset, action)) : assets
  const references = referenceQuery.data
  const managerOptions = (references?.managers ?? [])
    .filter((user) => user.enabled)
    .map((user) => ({ label: user.name, value: user.id }))
  const locationOptions = useMemo(() => {
    const flatten = (items: TreeItem[]): TreeItem[] =>
      items.flatMap((item) => [item, ...flatten(item.children ?? [])])
    if (references) {
      return flatten(references.locations)
        .filter((item) => item.status !== 'DISABLED')
        .map((item) => ({ label: `${item.name} · ${item.code}`, value: item.id }))
    }
    return (selfReferenceQuery.data?.locations ?? []).map((item) => ({
      label: `${item.name} · ${item.code}`,
      value: item.id,
    }))
  }, [references, selfReferenceQuery.data])
  const organizationOptions = useMemo(() => {
    const flatten = (items: TreeItem[]): TreeItem[] =>
      items.flatMap((item) => [item, ...flatten(item.children ?? [])])
    return flatten(references?.organizations ?? [])
      .filter((item) => item.status !== 'DISABLED')
      .map((item) => ({ label: item.name, value: item.id }))
  }, [references])
  const locationRegions = useMemo(() => {
    const flatten = (items: TreeItem[]): TreeItem[] =>
      items.flatMap((item) => [item, ...flatten(item.children ?? [])])
    return flatten(references?.locations ?? [])
      .filter(
        (item) =>
          item.status !== 'DISABLED' &&
          (item.parent_id === undefined || item.parent_id === null || item.is_selectable === false),
      )
      .map((item) => ({ label: item.name, value: item.id }))
  }, [references])
  const locationsByRegion = useMemo(() => {
    const flatten = (items: TreeItem[]): TreeItem[] =>
      items.flatMap((item) => [item, ...flatten(item.children ?? [])])
    const all = flatten(references?.locations ?? []).filter((item) => item.status !== 'DISABLED')
    const mapping: Record<number, Option[]> = {}
    all.forEach((item) => {
      if (item.is_selectable === false) return
      const regionId = item.parent_id ?? item.id
      mapping[regionId] = [...(mapping[regionId] ?? []), { label: item.name, value: item.id }]
    })
    return mapping
  }, [references])
  const categoryOptions = useMemo(
    () =>
      (selfReferenceQuery.data?.categories ?? []).map((item) => ({
        label: `${item.name} · ${item.code}`,
        value: item.id,
        disabled: (item.available_quantity ?? 0) < 1,
        availableQuantity: item.available_quantity ?? 0,
      })),
    [selfReferenceQuery.data],
  )
  const [employeeModalAssets, setEmployeeModalAssets] = useState<AssetSummary[]>([])
  const employeeModalAssetsQuery = useMemo<AssetSummary[]>(
    () =>
      (myAssetsQuery.data ?? []).map((asset) => ({
        id: asset.id,
        version: 1,
        asset_code: asset.asset_code,
        asset_name: asset.asset_name,
        category_name: '',
        status: asset.status,
        location_name: asset.location_name ?? '未设置地点',
        company_name: '',
        source_name: '',
        unit_name: '',
        purchase_date: '',
        purchase_amount: 0,
        information_complete: true,
        holder_user_id: currentUserId,
        usage_type: 'PERSONAL',
      })),
    [currentUserId, myAssetsQuery.data],
  )
  const mergedEmployeeModalAssets = useMemo(() => {
    const seen = new Set<number>()
    return [...employeeModalAssets, ...employeeModalAssetsQuery].filter((asset) => {
      if (seen.has(asset.id)) return false
      seen.add(asset.id)
      return true
    })
  }, [employeeModalAssets, employeeModalAssetsQuery])

  if (employeeTaskCenter) {
    return (
      <>
        <EmployeeTaskCenter
          onOpenRequest={(assetId) => {
            setEmployeeReturnAssetIds(assetId === undefined ? [] : [assetId])
            setUsageReturnInitialAction(assetId === undefined ? 'PERSONAL_USE' : 'PERSONAL_RETURN')
            setUsageReturnOpen(true)
          }}
          onOpenScanRequest={openWorkflowScan}
        />
        <UsageReturnModal
          open={usageReturnOpen}
          assets={mergedEmployeeModalAssets}
          scanOpen={scanOpen}
          onScanOpenChange={setScanOpen}
          onAssetsChange={setEmployeeModalAssets}
          users={[]}
          publicObjects={publicObjectQuery.data ?? []}
          organizations={organizationOptions}
          locationRegions={locationRegions}
          locationsByRegion={locationsByRegion}
          locations={locationOptions}
          categories={categoryOptions}
          availableActions={availableUsageReturnActions}
          currentUserId={currentUserId}
          selfService
          initialAction={
            employeeReturnAssetIds.length ? 'PERSONAL_RETURN' : usageReturnInitialAction
          }
          initialAssetIds={employeeReturnAssetIds}
          loading={usageReturnMutation.isPending}
          onCancel={() => {
            setUsageReturnOpen(false)
            setEmployeeReturnAssetIds([])
          }}
          onSubmit={(submission) => usageReturnMutation.mutate(submission)}
        />
        <BarcodeScanner
          open={workflowScanOpen}
          title="扫码提交领用 / 借用申请"
          onClose={() => setWorkflowScanOpen(false)}
          scanToUse
          preferredPurpose="USE"
          onDetected={() => undefined}
        />
      </>
    )
  }

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow="ASSET LIFECYCLE"
        title="让资产流转，每一步都有据可查"
        description="入库与领退继续走审批操作单；转移、维修和报废命令会校验权限、版本与业务锁，并写入资产履历和全局审计。"
        icon={ArrowLeftRight}
        tone="blue"
        actions={
          <>
            <Button
              size="large"
              icon={<RefreshCw size={17} />}
              loading={query.isFetching || syncFeishuApprovalsMutation.isPending}
              onClick={() => void syncFeishuApprovalsMutation.mutate()}
            >
              同步审批状态
            </Button>
            <Button
              type="primary"
              size="large"
              icon={<Plus size={17} />}
              onClick={() => navigate('/assets/new')}
            >
              发起入库申请
            </Button>
            {availableUsageReturnActions.length ? (
              <Button size="large" icon={<ScanLine size={17} />} onClick={openWorkflowScan}>
                扫码领用 / 借用
              </Button>
            ) : null}
            <Button
              size="large"
              icon={<ArrowLeftRight size={17} />}
              onClick={() => openAction('TRANSFER')}
            >
              资产转移
            </Button>
          </>
        }
        aside={
          <div className="operations-hero__aside-card">
            <span>审批流程总数</span>
            <strong>{query.data?.total ?? 0}</strong>
            <small>转移、维修与报废另写入资产履历</small>
          </div>
        }
      />

      <OperationsMetrics
        items={[
          { label: '审批处理中', value: pendingApproval, hint: '等待审批任务完成', tone: 'blue' },
          { label: '执行处理中', value: processing, hint: '后端正在变更资产状态', tone: 'amber' },
          { label: '已完成', value: completed, hint: '当前审批记录范围', tone: 'green' },
          {
            label: '执行失败',
            value: failed,
            hint: failed ? '请查看失败原因' : '当前没有异常',
            tone: failed ? 'red' : 'slate',
          },
        ]}
      />

      {canManageUsage && pendingExtensionsQuery.data?.length ? (
        <GlassPanel>
          <SectionHeading
            eyebrow="BORROW EXTENSIONS"
            title="借用延期待审批"
            description="员工提交的延期申请需要管理员明确批准或拒绝，批准后会同步新的归还时间。"
          />
          <div className="operations-table employee-task-center__request-table">
            <div className="operations-table__header">
              <span>申请</span>
              <span>原归还时间</span>
              <span>延期至</span>
              <span>原因</span>
              <span>操作</span>
            </div>
            {pendingExtensionsQuery.data.map((extension) => (
              <div key={extension.id} className="operations-table__row">
                <div className="operations-table__primary">
                  <strong>
                    {extension.request_no ?? `申请 #${extension.operation_request_id}`}
                  </strong>
                  <small>申请人 #{extension.applicant_id}</small>
                </div>
                <span>
                  {dayjs(extension.original_expected_return_at).format('YYYY-MM-DD HH:mm')}
                </span>
                <span>
                  {dayjs(extension.requested_expected_return_at).format('YYYY-MM-DD HH:mm')}
                </span>
                <span>{extension.reason}</span>
                <div className="operations-table__status-actions">
                  <Button
                    size="small"
                    type="primary"
                    loading={extensionReviewMutation.isPending}
                    onClick={() =>
                      Modal.confirm({
                        title: '批准借用延期？',
                        content: `归还时间将更新为 ${dayjs(extension.requested_expected_return_at).format('YYYY-MM-DD HH:mm')}`,
                        okText: '批准',
                        cancelText: '取消',
                        onOk: () =>
                          extensionReviewMutation.mutateAsync({
                            extensionId: extension.id,
                            approved: true,
                            opinion: '同意延期',
                          }),
                      })
                    }
                  >
                    批准
                  </Button>
                  <Button size="small" danger onClick={() => setExtensionReviewTarget(extension)}>
                    拒绝
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </GlassPanel>
      ) : null}

      {canManageUsage && pendingTransferHandoversQuery.data?.length ? (
        <GlassPanel>
          <SectionHeading
            eyebrow="TRANSFER HANDOVERS"
            title="待确认的资产交接"
            description="管理员发起交接后，先确认转出，再由接收员工确认收取，资产才会完成归属变更。"
          />
          <div className="operations-table">
            <div className="operations-table__header">
              <span>交接单</span>
              <span>资产</span>
              <span>接收人</span>
              <span>状态</span>
              <span>操作</span>
            </div>
            {pendingTransferHandoversQuery.data.map((handover) => (
              <div key={handover.id} className="operations-table__row">
                <div className="operations-table__primary">
                  <strong>{handover.handover_no}</strong>
                  <small>{dayjs(handover.created_at).format('YYYY-MM-DD HH:mm')}</small>
                </div>
                <span>{handover.items.map((item) => item.asset_code).join('、')}</span>
                <span>{handover.receiver_user?.name ?? '扫码接收人待确认'}</span>
                <StatusPill
                  label={handover.status === 'PENDING_OUTGOING' ? '待转出确认' : '待员工签收'}
                  tone={handover.status === 'PENDING_OUTGOING' ? 'amber' : 'blue'}
                />
                <div className="operations-table__status-actions">
                  {handover.status === 'PENDING_OUTGOING' ? (
                    <Button
                      size="small"
                      type="primary"
                      loading={transferHandoverMutation.isPending}
                      onClick={() =>
                        transferHandoverMutation.mutate({ id: handover.id, action: 'OUTGOING' })
                      }
                    >
                      确认转出
                    </Button>
                  ) : (
                    <span>等待接收人确认</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </GlassPanel>
      ) : null}

      <GlassPanel>
        <SectionHeading
          eyebrow="QUICK START"
          title="业务类型"
          description="从真实资产台账选择对象并执行对应业务。"
        />
        <div className="operations-grid operations-grid--five">
          {flowTypes.map(
            ({ name, description, icon: Icon, operationTypes, tone, action: cardAction }) => {
              const count = records.filter((record) =>
                operationTypes.includes(record.operation_type),
              ).length
              return (
                <button
                  key={name}
                  type="button"
                  className={`operations-card operations-tone--${tone}`}
                  onClick={() => {
                    if (cardAction === 'STOCK_IN') navigate('/assets/new')
                    else if (cardAction === 'INFO_CHANGE') {
                      informationChangeForm.resetFields()
                      informationChangeForm.setFieldsValue({
                        change_type: 'PHYSICAL',
                        asset_ids: [],
                        reason: '',
                      })
                      setInformationChangeOpen(true)
                    } else if (cardAction) openAction(cardAction)
                    else if (availableUsageReturnActions.length) setUsageReturnOpen(true)
                    else void message.warning('当前账号没有发起领用或退库的权限')
                  }}
                >
                  <span className="operations-card__icon">
                    <Icon aria-hidden="true" size={21} strokeWidth={1.8} />
                  </span>
                  <h3>{name}</h3>
                  <p>{description}</p>
                  <div className="operations-card__meta">
                    <span>{count} 条审批记录</span>
                    <ArrowUpRight aria-hidden="true" size={15} />
                  </div>
                </button>
              )
            },
          )}
        </div>
      </GlassPanel>

      <GlassPanel>
        <SectionHeading
          eyebrow="RECENT ACTIVITY"
          title="我的资产与业务"
          description="区分本人发起、发给本人、待签收、待归还、当前在用和收到的交接；管理员直接维护资产时，变更会写入资产履历和审计日志。"
          action={
            <Select
              value={filter}
              options={workflowViewOptions}
              onChange={setFilter}
              style={{ width: 190 }}
              aria-label="工作台视图"
            />
          }
        />
        {showingMyAssets && myAssetsQuery.isLoading ? (
          <div className="operations-loading">
            <Spin />
          </div>
        ) : showingMyAssets && myAssetsQuery.isError ? (
          <StatePanel
            mode="error"
            message="我的资产加载失败"
            retryLabel="重新加载"
            onRetry={() => void myAssetsQuery.refetch()}
          />
        ) : showingMyAssets && filteredMyAssets.length ? (
          <div className="operations-table">
            <div className="operations-table__header">
              <span>资产</span>
              <span>资产编号</span>
              <span>使用方式</span>
              <span>当前地点</span>
              <span>归还安排</span>
            </div>
            {filteredMyAssets.map((asset) => (
              <div key={asset.id} className="operations-table__row">
                <strong>{asset.asset_name}</strong>
                <div className="operations-table__primary">
                  <strong>{asset.asset_code}</strong>
                  <small>资产 #{asset.id}</small>
                </div>
                <span>{asset.usage_mode === 'BORROW' ? '借用' : '领用'}</span>
                <span>{asset.location_name ?? '未设置地点'}</span>
                <div className="operations-table__status-actions">
                  {asset.usage_mode === 'BORROW' ? (
                    <StatusPill
                      label={
                        asset.expected_return_at
                          ? `应于 ${dayjs(asset.expected_return_at).format('YYYY-MM-DD HH:mm')} 归还`
                          : '待归还'
                      }
                      tone={
                        asset.expected_return_at &&
                        dayjs(asset.expected_return_at).isBefore(dayjs())
                          ? 'red'
                          : 'amber'
                      }
                    />
                  ) : (
                    <StatusPill label="在用" tone="green" />
                  )}
                  {filter === 'PENDING_MY_RETURN' ? (
                    <Button size="small" onClick={() => setUsageReturnOpen(true)}>
                      发起个人退库
                    </Button>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        ) : showingMyAssets ? (
          <StatePanel mode="empty" message="当前视图暂无本人名下资产" />
        ) : query.isLoading ? (
          <div className="operations-loading">
            <Spin />
          </div>
        ) : query.isError ? (
          <StatePanel
            mode="error"
            message="流程数据加载失败"
            retryLabel="重新加载"
            onRetry={() => void query.refetch()}
          />
        ) : filteredRecords.length ? (
          <div className="operations-table">
            <div className="operations-table__header">
              <span>流程类型</span>
              <span>资产与单号</span>
              <span>发起人</span>
              <span>审批 / 执行</span>
              <span>状态</span>
            </div>
            {filteredRecords.map((record) => {
              const status = operationStatus(record)
              return (
                <div key={record.id} className="operations-table__row">
                  <strong>{operationTypeDisplayLabel(record)}</strong>
                  <div className="operations-table__primary">
                    <strong>{operationAssetLabel(record)}</strong>
                    <small>{record.request_no}</small>
                  </div>
                  <span>
                    {record.applicant_id === currentUserId ? '我' : `用户 #${record.applicant_id}`}
                  </span>
                  <span>
                    {approvalStatusLabel(record.approval_status)} /{' '}
                    {executionStatusLabel(record.execution_status)}
                  </span>
                  <div className="operations-table__status-actions">
                    <StatusPill label={status.label} tone={status.tone} />
                    {record.usage_mode === 'BORROW' && record.is_overdue ? (
                      <StatusPill label="已逾期" tone="red" />
                    ) : null}
                    <Button size="small" onClick={() => setWorkflowDetailId(record.id)}>
                      查看时间线
                    </Button>
                    {informationChangeOperationTypes.has(record.operation_type) ? (
                      <Button
                        size="small"
                        icon={<ClipboardPenLine size={13} />}
                        onClick={() => setInformationChangeDetailId(record.id)}
                      >
                        变更详情
                      </Button>
                    ) : null}
                    {record.applicant_id === currentUserId &&
                    record.operation_type === 'STOCK_IN' &&
                    record.approval_status === 'REJECTED' ? (
                      <Button
                        size="small"
                        type="primary"
                        icon={<Plus size={13} />}
                        onClick={() => navigate(`/assets/new?resubmit=${record.id}`)}
                      >
                        编辑后重提
                      </Button>
                    ) : null}
                    {canManageUsage &&
                    record.usage_mode === 'BORROW' &&
                    record.fulfillment_status === 'COMPLETED' &&
                    record.execution_status === 'SUCCESS' &&
                    !record.return_requested_at ? (
                      <Button
                        size="small"
                        icon={<RotateCcw size={13} />}
                        onClick={() => {
                          setReturnRequestTarget(record)
                          setReturnRequestReason('借用期限或业务需要，请尽快归还资产')
                        }}
                      >
                        要求归还
                      </Button>
                    ) : null}
                    {canManageUsage && record.allowed_actions?.includes('CONFIRM_RETURN') ? (
                      <Button
                        size="small"
                        type="primary"
                        icon={<PackageCheck size={13} />}
                        onClick={() => setReturnConfirmTarget(record)}
                      >
                        验收退库
                      </Button>
                    ) : null}
                    {canHandleLocalFeishuDecision(record, canManageUsage) ? (
                      <>
                        <Button
                          size="small"
                          type="primary"
                          loading={localFeishuActionMutation.isPending}
                          onClick={() =>
                            localFeishuActionMutation.mutate({
                              operationId: record.id,
                              operationType: record.operation_type,
                              action: 'APPROVE',
                              reason: '本地飞书模拟审批通过',
                            })
                          }
                        >
                          同意申请
                        </Button>
                        <Button
                          size="small"
                          danger
                          loading={localFeishuActionMutation.isPending}
                          onClick={() =>
                            Modal.confirm({
                              title:
                                record.operation_type === 'PERSONAL_RETURN'
                                  ? '拒绝这条退库申请？'
                                  : '拒绝这条领用申请？',
                              content:
                                record.operation_type === 'PERSONAL_RETURN'
                                  ? '拒绝后申请不会进入管理员验收退库环节。'
                                  : '拒绝后申请不会进入管理员发放环节。',
                              okText: '确认拒绝',
                              cancelText: '取消',
                              onOk: () =>
                                localFeishuActionMutation.mutateAsync({
                                  operationId: record.id,
                                  operationType: record.operation_type,
                                  action: 'REJECT',
                                  reason: '本地飞书模拟审批拒绝',
                                }),
                            })
                          }
                        >
                          拒绝申请
                        </Button>
                      </>
                    ) : null}
                    {canHandleInternalDecision(record, canManageUsage)
                      ? (() => {
                          const approvalTask = pendingApprovalTaskByOperationId.get(record.id)
                          if (!approvalTask) return null
                          return (
                            <>
                              <Button
                                size="small"
                                type="primary"
                                loading={internalApprovalMutation.isPending}
                                onClick={() =>
                                  internalApprovalMutation.mutate({
                                    taskId: approvalTask.id,
                                    action: 'APPROVE',
                                    opinion: '同意申请',
                                  })
                                }
                              >
                                同意申请
                              </Button>
                              <Button
                                size="small"
                                danger
                                loading={internalApprovalMutation.isPending}
                                onClick={() =>
                                  Modal.confirm({
                                    title:
                                      record.operation_type === 'PERSONAL_RETURN'
                                        ? '拒绝这条退库申请？'
                                        : '拒绝这条领用申请？',
                                    content: '拒绝后将通知申请人，资产状态保持不变。',
                                    okText: '确认拒绝',
                                    cancelText: '取消',
                                    onOk: () =>
                                      internalApprovalMutation.mutateAsync({
                                        taskId: approvalTask.id,
                                        action: 'REJECT',
                                        opinion: '管理员拒绝申请',
                                      }),
                                  })
                                }
                              >
                                拒绝申请
                              </Button>
                            </>
                          )
                        })()
                      : null}
                    {canManageUsage &&
                    record.operation_type === 'PERSONAL_USE' &&
                    (record.approval_status === 'PENDING' ||
                      record.approval_status === 'APPROVED') &&
                    (record.fulfillment_status === 'PENDING_ISSUE' ||
                      record.fulfillment_status === 'SIGN_REFUSED') ? (
                      <Button
                        size="small"
                        type="primary"
                        icon={<PackageCheck size={13} />}
                        loading={fulfillmentMutation.isPending}
                        onClick={() => {
                          setIssueTarget(record)
                          setSelectedIssueAssetIds([])
                          setIssueRemark('管理员已核对申请并通过发放')
                        }}
                      >
                        审批并发放
                      </Button>
                    ) : null}
                    {record.target_user_id === currentUserId &&
                    record.fulfillment_status === 'PENDING_SIGN' ? (
                      <>
                        <Button
                          size="small"
                          type="primary"
                          loading={fulfillmentMutation.isPending}
                          onClick={() =>
                            fulfillmentMutation.mutate({
                              operationId: record.id,
                              action: 'SIGN',
                              remark: '员工确认收到资产',
                            })
                          }
                        >
                          员工签收
                        </Button>
                        <Button
                          size="small"
                          danger
                          loading={fulfillmentMutation.isPending}
                          onClick={() =>
                            Modal.confirm({
                              title: '拒绝签收这批资产？',
                              content: '拒绝后申请会回到待发放状态，管理员可以重新发放。',
                              okText: '确认拒绝',
                              cancelText: '取消',
                              onOk: () =>
                                fulfillmentMutation.mutateAsync({
                                  operationId: record.id,
                                  action: 'REFUSE_SIGN',
                                  remark: '员工拒绝签收本次发放的资产',
                                }),
                            })
                          }
                        >
                          拒绝签收
                        </Button>
                      </>
                    ) : null}
                    {record.applicant_id === currentUserId &&
                    record.approval_status === 'PENDING' ? (
                      <>
                        <Button
                          size="small"
                          icon={<Trash2 size={13} />}
                          onClick={() => setWithdrawTarget(record)}
                        >
                          撤回申请
                        </Button>
                        <Button
                          size="small"
                          icon={<Bell size={13} />}
                          disabled={
                            Boolean(record.next_remind_at) &&
                            dayjs(record.next_remind_at).isAfter(dayjs())
                          }
                          onClick={() => {
                            setRemindTarget(record)
                            setRemindReason('请及时处理当前审批申请')
                          }}
                        >
                          {record.next_remind_at && dayjs(record.next_remind_at).isAfter(dayjs())
                            ? `${dayjs(record.next_remind_at).format('HH:mm')} 后可催`
                            : '催办'}
                        </Button>
                      </>
                    ) : null}
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <StatePanel mode="empty" message="当前筛选下暂无流程记录" />
        )}
      </GlassPanel>

      <UsageReturnModal
        open={usageReturnOpen}
        assets={[...managerModalAssets, ...assets]}
        scanOpen={scanOpen}
        onScanOpenChange={setScanOpen}
        onAssetsChange={setManagerModalAssets}
        users={(referenceQuery.data?.managers ?? [])
          .filter((user) => user.enabled)
          .map((user) => ({ label: user.name, value: user.id }))}
        publicObjects={publicObjectQuery.data ?? []}
        organizations={organizationOptions}
        locationRegions={locationRegions}
        locationsByRegion={locationsByRegion}
        locations={locationOptions}
        categories={categoryOptions}
        availableActions={availableUsageReturnActions}
        currentUserId={currentUserId}
        selfService={!canManageUsage && canSelfUsage}
        initialAction={usageReturnInitialAction}
        loading={usageReturnMutation.isPending}
        onCancel={() => {
          setUsageReturnOpen(false)
          setUsageReturnInitialAction(undefined)
          setEmployeeReturnAssetIds([])
        }}
        onSubmit={(submission) => usageReturnMutation.mutate(submission)}
      />

      <BarcodeScanner
        open={workflowScanOpen}
        title="扫码提交领用 / 借用申请"
        onClose={() => setWorkflowScanOpen(false)}
        scanToUse
        preferredPurpose="USE"
        onDetected={() => undefined}
      />

      <ReturnConfirmModal
        target={returnConfirmTarget}
        organizations={organizationOptions}
        locationRegions={locationRegions}
        locationsByRegion={locationsByRegion}
        loading={returnConfirmMutation.isPending}
        onCancel={() => setReturnConfirmTarget(null)}
        onSubmit={(payload) => {
          if (!returnConfirmTarget) return
          returnConfirmMutation.mutate({ operationId: returnConfirmTarget.id, payload })
        }}
      />

      <Modal
        open={issueTarget !== null}
        title={issueTarget ? `审批并发放 · ${issueTarget.request_no}` : '审批并发放'}
        className="operations-glass-modal"
        width={720}
        okText="审批通过并发放"
        cancelText="取消"
        confirmLoading={fulfillmentMutation.isPending}
        okButtonProps={{
          disabled:
            issueCandidatesQuery.isLoading ||
            selectedIssueAssetIds.length !==
              (issueCandidatesQuery.data?.requested_quantity ?? Number.NaN) ||
            issueRegionId === undefined ||
            issueLocationId === undefined,
        }}
        onCancel={() => {
          setIssueTarget(null)
          setSelectedIssueAssetIds([])
          setIssueRegionId(undefined)
          setIssueLocationId(undefined)
        }}
        onOk={() => {
          if (!issueTarget) return
          fulfillmentMutation.mutate({
            operationId: issueTarget.id,
            action: 'ISSUE',
            assetIds: selectedIssueAssetIds,
            regionId: issueRegionId,
            locationId: issueLocationId,
            remark: issueRemark,
          })
        }}
        destroyOnHidden
      >
        {issueCandidatesQuery.isLoading ? (
          <div className="operations-loading">
            <Spin />
          </div>
        ) : issueCandidatesQuery.isError ? (
          <StatePanel
            mode="error"
            message="可发放资产加载失败"
            retryLabel="重新加载"
            onRetry={() => void issueCandidatesQuery.refetch()}
          />
        ) : issueCandidatesQuery.data ? (
          <div className="operations-issue-picker">
            <p className="operations-modal-note">
              {issueCandidatesQuery.data.requested_category
                ? `申请类别：${issueCandidatesQuery.data.requested_category.name} · `
                : ''}
              需选择 {issueCandidatesQuery.data.requested_quantity} 件，已选择{' '}
              {selectedIssueAssetIds.length}{' '}
              件。审批通过后资产将变为“领用待确认”，员工签收后转为“在用”。
            </p>
            <Select
              mode="multiple"
              value={selectedIssueAssetIds}
              placeholder="请选择本次实际发放的具体资产"
              showSearch
              optionFilterProp="searchText"
              style={{ width: '100%' }}
              onChange={(values: number[]) => {
                if (values.length > issueCandidatesQuery.data.requested_quantity) {
                  void message.warning(
                    `本申请最多选择 ${issueCandidatesQuery.data.requested_quantity} 件资产`,
                  )
                  return
                }
                setSelectedIssueAssetIds(values)
              }}
              options={issueCandidatesQuery.data.items.map((asset) => ({
                value: asset.id,
                searchText: [
                  asset.asset_code,
                  asset.asset_name,
                  asset.specification_model,
                  asset.serial_number,
                  asset.organization_name,
                  asset.location_name,
                ]
                  .filter(Boolean)
                  .join(' '),
                label: `${asset.asset_code} · ${asset.asset_name}${
                  asset.specification_model ? ` · ${asset.specification_model}` : ''
                }${asset.serial_number ? ` · SN ${asset.serial_number}` : ''}${
                  asset.organization_name ? ` · ${asset.organization_name}` : ''
                }${asset.location_name ? ` · ${asset.location_name}` : ''}`,
              }))}
              notFoundContent="当前没有符合申请条件且可发放的闲置资产"
            />
            <div className="operations-form-grid">
              <Select
                value={issueRegionId}
                placeholder="请选择领用后区域"
                showSearch
                optionFilterProp="label"
                options={locationRegions}
                style={{ width: '100%' }}
                onChange={(value: number) => {
                  setIssueRegionId(value)
                  setIssueLocationId(undefined)
                }}
              />
              <Select
                value={issueLocationId}
                placeholder="请选择领用后存放地点"
                showSearch
                optionFilterProp="label"
                options={locationsByRegion[issueRegionId ?? 0] ?? []}
                style={{ width: '100%' }}
                disabled={issueRegionId === undefined}
                onChange={setIssueLocationId}
              />
            </div>
            <Input.TextArea
              value={issueRemark}
              rows={3}
              maxLength={2000}
              showCount
              placeholder="审批 / 发放备注（选填）"
              style={{ marginTop: 16 }}
              onChange={(event) => setIssueRemark(event.target.value)}
            />
          </div>
        ) : null}
      </Modal>

      <Modal
        open={action !== null}
        title={action ? actionMeta[action].title : ''}
        className="operations-glass-modal"
        okText={action ? actionMeta[action].submit : '确认'}
        cancelText="取消"
        confirmLoading={mutation.isPending}
        onCancel={() => setAction(null)}
        onOk={() => form.submit()}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={(values) => mutation.mutate(values)}>
          <Form.Item
            name="asset_ids"
            label="选择资产"
            rules={[{ required: true, message: '请选择至少一件资产' }]}
          >
            <Select
              mode="multiple"
              showSearch
              optionFilterProp="label"
              loading={assetQuery.isLoading}
              placeholder="按资产名称或编码选择"
              options={selectableAssets.map((asset) => ({
                label: `${asset.asset_name} · ${asset.asset_code}`,
                value: asset.id,
              }))}
            />
          </Form.Item>
          {action === 'TRANSFER' ? (
            <>
              <Form.Item name="holder_user_id" label="新使用人">
                <Select
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  options={managerOptions}
                  placeholder="不修改可留空"
                />
              </Form.Item>
              <Form.Item name="manager_id" label="新责任管理员">
                <Select
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  options={managerOptions}
                  placeholder="不修改可留空"
                />
              </Form.Item>
              <Form.Item name="location_id" label="新存放地点">
                <Select
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  options={locationOptions}
                  placeholder="不修改可留空"
                />
              </Form.Item>
            </>
          ) : null}
          {action === 'REPAIR_START' ? (
            <>
              <Form.Item name="vendor" label="维修单位">
                <Input maxLength={128} placeholder="可选" />
              </Form.Item>
              <Form.Item name="estimated_cost" label="预计维修金额">
                <InputNumber min={0} precision={2} prefix="¥" style={{ width: '100%' }} />
              </Form.Item>
            </>
          ) : null}
          {action === 'REPAIR_COMPLETE' ? (
            <Form.Item name="actual_cost" label="实际维修金额">
              <InputNumber min={0} precision={2} prefix="¥" style={{ width: '100%' }} />
            </Form.Item>
          ) : null}
          {action === 'SCRAP' ? (
            <>
              <Form.Item
                noStyle
                shouldUpdate={(previous, current) => previous.asset_ids !== current.asset_ids}
              >
                {({ getFieldValue }) => {
                  const selectedIds = (getFieldValue('asset_ids') ?? []) as number[]
                  return selectedIds.length ? (
                    <div className="operations-scrap-details">
                      {selectedIds.map((assetId) => {
                        const asset = assets.find((item) => item.id === assetId)
                        return (
                          <div key={assetId} className="operations-scrap-detail">
                            <strong>
                              {asset?.asset_code ?? `资产 #${assetId}`} · {asset?.asset_name ?? ''}
                            </strong>
                            <Form.Item
                              name={['scrap_details', String(assetId), 'disposal_date']}
                              label="实际处置日期"
                              initialValue={dayjs()}
                              rules={[{ required: true, message: '请选择实际处置日期' }]}
                            >
                              <DatePicker style={{ width: '100%' }} />
                            </Form.Item>
                            <Form.Item
                              name={['scrap_details', String(assetId), 'scrap_amount']}
                              label="回收金额"
                              rules={[{ required: true, message: '请填写回收金额，可填写 0' }]}
                            >
                              <InputNumber
                                min={0}
                                precision={2}
                                prefix="¥"
                                style={{ width: '100%' }}
                              />
                            </Form.Item>
                            <Form.Item
                              name={['scrap_details', String(assetId), 'disposition']}
                              label="处置方式"
                            >
                              <Input maxLength={255} placeholder="例如：出售、回收、捐赠或拆解" />
                            </Form.Item>
                            <Form.Item
                              name={['scrap_details', String(assetId), 'disposition_remark']}
                              label="处置备注"
                            >
                              <Input.TextArea
                                maxLength={1000}
                                rows={2}
                                placeholder="填写回收商、处置批次等说明"
                              />
                            </Form.Item>
                          </div>
                        )
                      })}
                    </div>
                  ) : null
                }}
              </Form.Item>
              <Form.Item name="child_action" label="主资产的附属资产处理">
                <Select
                  options={[
                    { label: '存在附属资产时阻止报废', value: 'BLOCK' },
                    { label: '解除关系后仅报废主资产', value: 'DETACH' },
                    { label: '主附资产一起报废（附属资产回收金额默认 0）', value: 'SCRAP' },
                  ]}
                />
              </Form.Item>
            </>
          ) : null}
          <Form.Item
            name="reason"
            label={action === 'REPAIR_COMPLETE' ? '维修结果' : '业务原因'}
            rules={[{ required: true, min: 2, message: '请填写至少 2 个字' }]}
          >
            <Input.TextArea
              rows={4}
              maxLength={500}
              showCount
              placeholder="保存后会写入资产履历与审计记录"
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={informationChangeOpen}
        title="新建资产信息变更单"
        className="operations-glass-modal"
        okText="提交审批"
        cancelText="取消"
        width={720}
        confirmLoading={informationChangeMutation.isPending}
        onCancel={() => setInformationChangeOpen(false)}
        onOk={() => informationChangeForm.submit()}
        destroyOnHidden
      >
        <Form
          form={informationChangeForm}
          layout="vertical"
          onFinish={(values) => informationChangeMutation.mutate(values)}
        >
          <Form.Item name="change_type" label="变更单类型" rules={[{ required: true }]}>
            <Segmented
              block
              options={[
                { label: '实物信息变更', value: 'PHYSICAL' },
                { label: '财务信息变更', value: 'FINANCIAL' },
                { label: '维保信息变更', value: 'WARRANTY' },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="asset_ids"
            label="选择资产"
            rules={[{ required: true, message: '请选择至少一件资产' }]}
          >
            <Select
              mode="multiple"
              showSearch
              optionFilterProp="label"
              options={assets
                .filter((asset) => asset.status !== 'SCRAPPED')
                .map((asset) => ({
                  value: asset.id,
                  label: `${asset.asset_name} · ${asset.asset_code}`,
                }))}
            />
          </Form.Item>
          <Form.Item
            noStyle
            shouldUpdate={(previous, current) => previous.change_type !== current.change_type}
          >
            {({ getFieldValue }) => {
              const changeType = getFieldValue('change_type') as InformationChangeType
              if (changeType === 'PHYSICAL') {
                return (
                  <>
                    <Form.Item name="asset_name" label="变更后资产名称">
                      <Input maxLength={255} />
                    </Form.Item>
                    <Form.Item name="location_id" label="变更后存放地点">
                      <Select
                        allowClear
                        showSearch
                        optionFilterProp="label"
                        options={locationOptions}
                      />
                    </Form.Item>
                    <Form.Item name="manager_id" label="变更后责任管理员">
                      <Select
                        allowClear
                        showSearch
                        optionFilterProp="label"
                        options={managerOptions}
                      />
                    </Form.Item>
                  </>
                )
              }
              if (changeType === 'FINANCIAL') {
                return (
                  <>
                    <Form.Item name="original_amount" label="变更后金额">
                      <InputNumber min={0} precision={2} prefix="¥" style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="zero_amount_reason" label="零金额原因">
                      <Input maxLength={255} />
                    </Form.Item>
                    <Form.Item name="purchase_date" label="变更后购入日期">
                      <DatePicker style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="service_life_months" label="变更后使用期限（月）">
                      <InputNumber min={1} max={1200} style={{ width: '100%' }} />
                    </Form.Item>
                  </>
                )
              }
              return (
                <>
                  <Form.Item name="warranty_supplier_id" label="维保供应商">
                    <Select
                      allowClear
                      showSearch
                      optionFilterProp="label"
                      options={(references?.suppliers ?? []).map((item) => ({
                        label: item.name,
                        value: item.id,
                      }))}
                    />
                  </Form.Item>
                  <Form.Item name="warranty_contact" label="维保联系人">
                    <Input maxLength={128} />
                  </Form.Item>
                  <Form.Item name="warranty_phone" label="维保电话">
                    <Input maxLength={64} />
                  </Form.Item>
                  <Form.Item name="warranty_expiry_date" label="维保到期日">
                    <DatePicker style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item name="warranty_description" label="维保说明">
                    <Input.TextArea rows={3} maxLength={2000} />
                  </Form.Item>
                </>
              )
            }}
          </Form.Item>
          <Form.Item
            name="reason"
            label="变更原因"
            rules={[{ required: true, min: 2, message: '请填写变更原因' }]}
          >
            <Input.TextArea rows={3} maxLength={500} showCount />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={workflowDetailId !== null}
        title={
          workflowDetailQuery.data
            ? `业务时间线 · ${workflowDetailQuery.data.request_no}`
            : '业务时间线'
        }
        className="operations-glass-modal"
        width={780}
        footer={null}
        onCancel={() => setWorkflowDetailId(null)}
      >
        {workflowDetailQuery.isLoading ? (
          <div className="operations-loading">
            <Spin />
          </div>
        ) : workflowDetailQuery.isError ? (
          <StatePanel
            mode="error"
            message="业务详情加载失败"
            retryLabel="重新加载"
            onRetry={() => void workflowDetailQuery.refetch()}
          />
        ) : workflowDetailQuery.data ? (
          <WorkflowTimeline
            detail={workflowDetailQuery.data}
            onDownload={downloadWorkflowEvidence}
          />
        ) : null}
      </Modal>

      <InformationChangeDetailModal
        open={informationChangeDetailId !== null}
        detail={informationChangeDetailQuery.data}
        loading={informationChangeDetailQuery.isLoading}
        error={informationChangeDetailQuery.isError}
        currentUserId={currentUserId}
        users={references?.managers ?? []}
        onRetry={() => void informationChangeDetailQuery.refetch()}
        onClose={() => setInformationChangeDetailId(null)}
      />

      <Modal
        open={returnRequestTarget !== null}
        title={`要求归还 ${returnRequestTarget?.request_no ?? ''}`}
        className="operations-glass-modal"
        okText="确认要求归还"
        cancelText="取消"
        confirmLoading={borrowReturnRequestMutation.isPending}
        onCancel={() => {
          setReturnRequestTarget(null)
          setReturnRequestReason('')
        }}
        onOk={() => {
          const reason = returnRequestReason.trim()
          if (!returnRequestTarget || reason.length < 2) {
            void message.warning('请填写要求归还原因')
            return
          }
          borrowReturnRequestMutation.mutate({
            operationId: returnRequestTarget.id,
            reason,
          })
        }}
      >
        <div className="operations-modal-fields">
          <label>
            <span>归还原因</span>
            <Input.TextArea
              value={returnRequestReason}
              rows={4}
              maxLength={2000}
              showCount
              placeholder="请说明要求员工归还资产的原因"
              onChange={(event) => setReturnRequestReason(event.target.value)}
            />
          </label>
        </div>
      </Modal>

      <Modal
        open={remindTarget !== null}
        title={`催办 ${remindTarget?.request_no ?? ''}`}
        className="operations-glass-modal"
        okText="确认催办"
        cancelText="取消"
        confirmLoading={reminderMutation.isPending}
        onCancel={() => {
          setRemindTarget(null)
          setRemindReason('')
        }}
        onOk={() => {
          const reason = remindReason.trim()
          if (!remindTarget || reason.length < 2) {
            void message.warning('请填写催办说明')
            return
          }
          reminderMutation.mutate({ operationId: remindTarget.id, reason })
        }}
      >
        <div className="operations-modal-fields">
          <label>
            <span>催办说明</span>
            <Input.TextArea
              value={remindReason}
              rows={4}
              maxLength={500}
              showCount
              placeholder="请填写催办说明（至少 2 个字）"
              onChange={(event) => setRemindReason(event.target.value)}
            />
          </label>
          <p className="operations-modal-note">
            当前实现会生成系统内催办与审计记录，并按每个申请一小时一次进行频控；未接入正式飞书通知。
          </p>
        </div>
      </Modal>
      <Modal
        open={withdrawTarget !== null}
        title={`撤回申请 ${withdrawTarget?.request_no ?? ''}`}
        className="operations-glass-modal"
        okText="确认撤回"
        cancelText="取消"
        confirmLoading={withdrawMutation.isPending}
        onCancel={() => {
          setWithdrawTarget(null)
          setWithdrawReason('')
        }}
        onOk={() => {
          const reason = withdrawReason.trim()
          if (!withdrawTarget || reason.length < 2) {
            void message.warning('请填写撤回原因')
            return
          }
          withdrawMutation.mutate({ operationId: withdrawTarget.id, reason })
        }}
      >
        <div className="operations-modal-fields">
          <label>
            <span>撤回原因</span>
            <Input.TextArea
              value={withdrawReason}
              rows={4}
              maxLength={500}
              showCount
              placeholder="请填写撤回原因（至少 2 个字）"
              onChange={(event) => setWithdrawReason(event.target.value)}
            />
          </label>
          <p className="operations-modal-note">
            撤回后该申请结束，资产解除占用；如仍需退库，可重新提交新的退库申请。
          </p>
        </div>
      </Modal>
      <Modal
        open={extensionReviewTarget !== null}
        title="拒绝借用延期"
        okText="确认拒绝"
        cancelText="取消"
        confirmLoading={extensionReviewMutation.isPending}
        onCancel={() => setExtensionReviewTarget(null)}
        onOk={() => {
          const opinion = (
            document.querySelector('[data-extension-review-opinion]') as HTMLTextAreaElement | null
          )?.value.trim()
          if (!opinion) {
            void message.error('请填写拒绝原因')
            return
          }
          if (extensionReviewTarget) {
            extensionReviewMutation.mutate({
              extensionId: extensionReviewTarget.id,
              approved: false,
              opinion,
            })
          }
        }}
      >
        <Input.TextArea
          data-extension-review-opinion
          rows={4}
          placeholder="请填写拒绝原因"
          maxLength={500}
          showCount
        />
      </Modal>
    </div>
  )
}
