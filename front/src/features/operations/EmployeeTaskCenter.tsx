import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Button,
  DatePicker,
  Form,
  Input,
  Modal,
  Pagination,
  Select,
  Space,
  Spin,
  Timeline,
  message,
} from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import {
  ClipboardList,
  Download,
  PackageCheck,
  Plus,
  RotateCcw,
  ScanLine,
  Search,
} from 'lucide-react'
import { assetUsageReturnApi } from '@/api/assetUsageReturn'
import { attachmentApi } from '@/api/attachments'
import WorkflowEvidenceUpload from './WorkflowEvidenceUpload'
import { assetManagementApi, type TransferHandover } from '@/api/assetManagement'
import {
  workbenchApi,
  type ReturnState,
  type WorkbenchAsset,
  type WorkbenchQuery,
  type WorkbenchRequest,
  type WorkbenchView,
} from '@/api/workbench'
import StatePanel from '@/components/ui/StatePanel'
import {
  operationTypeLabel,
  workflowHandlerRoleLabel,
  workflowStatusLabel,
} from '@/utils/displayLabels'
import {
  GlassPanel,
  OperationsHero,
  OperationsMetrics,
  SectionHeading,
  StatusPill,
} from './OperationsUI'

interface EmployeeTaskCenterProps {
  onOpenRequest: (assetId?: number) => void
  onOpenScanRequest: () => void
}

const viewOptions: Array<{ value: WorkbenchView; label: string }> = [
  { value: 'my-requests', label: '我发起的申请' },
  { value: 'assigned-to-me', label: '发给我的资产' },
  { value: 'pending-sign', label: '待我签收' },
  { value: 'pending-return', label: '待我归还' },
  { value: 'my-assets', label: '我的在用资产' },
  { value: 'my-borrowed', label: '我的借用资产' },
  { value: 'received-handovers', label: '我收到的交接' },
]

const statusMeta: Record<
  string,
  { label: string; tone: 'blue' | 'amber' | 'green' | 'red' | 'slate' }
> = {
  PENDING_APPROVAL: { label: '审批中', tone: 'blue' },
  PENDING_ISSUE: { label: '待管理员发放', tone: 'amber' },
  PENDING_SIGN: { label: '待我签收', tone: 'amber' },
  SIGN_REFUSED: { label: '已拒收，待重新发放', tone: 'red' },
  PENDING_HANDOVER: { label: '待我交还', tone: 'amber' },
  PENDING_INSPECTION: { label: '待管理员验收', tone: 'amber' },
  RETURN_PROCESSING: { label: '退库处理中', tone: 'blue' },
  PROCESSING: { label: '执行中', tone: 'blue' },
  COMPLETED: { label: '已完成', tone: 'green' },
  REJECTED: { label: '已拒绝', tone: 'red' },
  WITHDRAWN: { label: '已撤回', tone: 'slate' },
  FAILED: { label: '执行失败', tone: 'red' },
  TERMINATED: { label: '已终止', tone: 'slate' },
}

const returnMeta: Record<
  ReturnState,
  { label: string; tone: 'amber' | 'green' | 'red' | 'slate' | 'blue' }
> = {
  NOT_BORROWED: { label: '在用', tone: 'green' },
  NORMAL: { label: '正常借用', tone: 'green' },
  DUE_SOON: { label: '即将到期', tone: 'amber' },
  DUE_TODAY: { label: '今日到期', tone: 'amber' },
  OVERDUE: { label: '已逾期', tone: 'red' },
  MANAGER_REQUESTED: { label: '管理员要求归还', tone: 'red' },
  RETURN_PROCESSING: { label: '退库申请中', tone: 'blue' },
  PENDING_INSPECTION: { label: '待管理员验收', tone: 'amber' },
}

const isAssetView = (view: WorkbenchView): view is 'pending-return' | 'my-assets' | 'my-borrowed' =>
  view === 'pending-return' || view === 'my-assets' || view === 'my-borrowed'

const assetLabel = (record: WorkbenchRequest): string => {
  if (record.assets.length) return record.assets.map((item) => item.asset_name).join('、')
  if (record.requested_category)
    return `${record.requested_category.name} × ${record.requested_quantity ?? 1}`
  return '待管理员分配资产'
}

export default function EmployeeTaskCenter({
  onOpenRequest,
  onOpenScanRequest,
}: EmployeeTaskCenterProps) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const downloadEvidence = async (attachmentId: number, filename: string) => {
    try {
      const blob = await attachmentApi.download(attachmentId)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      link.click()
      URL.revokeObjectURL(url)
    } catch (error: unknown) {
      const messageText = error instanceof Error ? error.message : '履约证据下载失败'
      void message.error(messageText)
    }
  }
  const [view, setView] = useState<WorkbenchView>('pending-sign')
  const [page, setPage] = useState(0)
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState<string>()
  const [dates, setDates] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const [detailId, setDetailId] = useState<number | null>(null)
  const [extensionTarget, setExtensionTarget] = useState<WorkbenchAsset | null>(null)
  const [handoverRejectTarget, setHandoverRejectTarget] = useState<TransferHandover | null>(null)
  const [handoverRejectReason, setHandoverRejectReason] = useState('')
  const [extensionForm] = Form.useForm<{ requested_expected_return_at: Dayjs; reason: string }>()
  const params = useMemo<WorkbenchQuery>(
    () => ({
      page,
      size: 20,
      keyword: keyword.trim() || undefined,
      status,
      start_date: dates?.[0]?.startOf('day').toISOString(),
      end_date: dates?.[1]?.endOf('day').toISOString(),
      pending_only: view === 'pending-return',
    }),
    [dates, keyword, page, status, view],
  )
  const summaryQuery = useQuery({
    queryKey: ['workbench', 'summary'],
    queryFn: workbenchApi.summary,
  })
  const requestQuery = useQuery({
    queryKey: ['workbench', view, params],
    queryFn: () => workbenchApi.requests(view, params),
    enabled: !isAssetView(view) && view !== 'received-handovers',
  })
  const assetQuery = useQuery({
    queryKey: ['workbench', view, params],
    queryFn: () =>
      workbenchApi.assets(view as 'pending-return' | 'my-assets' | 'my-borrowed', params),
    enabled: isAssetView(view),
  })
  const receivedHandoversQuery = useQuery({
    queryKey: ['transfer-handovers', 'received'],
    queryFn: assetManagementApi.receivedTransferHandovers,
    enabled: view === 'received-handovers',
  })
  const detailQuery = useQuery({
    queryKey: ['workbench', 'detail', detailId],
    queryFn: () => {
      if (detailId === null) throw new Error('未选择申请')
      return workbenchApi.detail(detailId)
    },
    enabled: detailId !== null,
  })
  const extensionQuery = useQuery({
    queryKey: ['borrow-extensions', extensionTarget?.usage_request_id],
    queryFn: () => {
      if (
        extensionTarget?.usage_request_id === null ||
        extensionTarget?.usage_request_id === undefined
      )
        throw new Error('当前资产没有对应借用申请')
      return assetUsageReturnApi.listBorrowExtensions(extensionTarget.usage_request_id)
    },
    enabled:
      extensionTarget?.usage_request_id !== null && extensionTarget?.usage_request_id !== undefined,
  })
  const extensionMutation = useMutation({
    mutationFn: async (values: { requested_expected_return_at: Dayjs; reason: string }) => {
      if (!extensionTarget?.usage_request_id) throw new Error('当前资产没有对应借用申请')
      return assetUsageReturnApi.createBorrowExtension(extensionTarget.usage_request_id, {
        requested_expected_return_at: values.requested_expected_return_at.toISOString(),
        reason: values.reason,
      })
    },
    onSuccess: async () => {
      setExtensionTarget(null)
      extensionForm.resetFields()
      await message.success('延期申请已提交，等待管理员审批')
      await queryClient.invalidateQueries({ queryKey: ['workbench'] })
      await queryClient.invalidateQueries({ queryKey: ['borrow-extensions'] })
    },
    onError: (error: Error) => void message.error(error.message),
  })

  const fulfillmentMutation = useMutation({
    mutationFn: ({ id, action }: { id: number; action: 'SIGN' | 'REFUSE_SIGN' }) =>
      action === 'SIGN'
        ? assetUsageReturnApi.sign(id, '员工已确认收到资产')
        : assetUsageReturnApi.refuseSign(id, '员工拒绝签收，请管理员重新核对'),
    onSuccess: async (_result, variables) => {
      await message.success(variables.action === 'SIGN' ? '签收成功，资产已转为在用' : '已拒绝签收')
      await queryClient.invalidateQueries({ queryKey: ['workbench'] })
    },
    onError: (error: Error) => void message.error(error.message),
  })

  const receivedHandoverMutation = useMutation({
    mutationFn: ({
      id,
      action,
      reason,
    }: {
      id: number
      action: 'RECEIVE' | 'REJECT'
      reason?: string
    }) =>
      action === 'RECEIVE'
        ? assetManagementApi.confirmTransferReceipt(id, '员工已确认收到交接资产')
        : assetManagementApi.rejectTransferHandover(id, reason ?? '员工拒绝接收交接资产'),
    onSuccess: async (_result, variables) => {
      await message.success(
        variables.action === 'RECEIVE' ? '交接完成，资产已归入我的在用资产' : '已拒绝该交接',
      )
      await queryClient.invalidateQueries({ queryKey: ['transfer-handovers'] })
      await queryClient.invalidateQueries({ queryKey: ['workbench'] })
      await queryClient.invalidateQueries({ queryKey: ['assets'] })
    },
    onError: (error: Error) => void message.error(error.message),
  })

  const pageData = isAssetView(view) ? assetQuery.data : requestQuery.data
  const isReceivedHandoverView = view === 'received-handovers'
  const loading = isReceivedHandoverView
    ? receivedHandoversQuery.isLoading
    : isAssetView(view)
      ? assetQuery.isLoading
      : requestQuery.isLoading
  const failed = isReceivedHandoverView
    ? receivedHandoversQuery.isError
    : isAssetView(view)
      ? assetQuery.isError
      : requestQuery.isError
  const summary = summaryQuery.data

  const resetPage = () => setPage(0)
  const changeView = (next: WorkbenchView) => {
    setView(next)
    setStatus(undefined)
    resetPage()
  }

  return (
    <div className="operations-page employee-task-center">
      <OperationsHero
        eyebrow="EMPLOYEE TASK CENTER"
        title="我的资产任务中心"
        description="从“我要领用”提交申请，再到审批、发放、签收、归还，全流程进度随时可查。"
        icon={ClipboardList}
        tone="blue"
        actions={
          <>
            <Button
              type="primary"
              size="large"
              icon={<Plus size={17} />}
              onClick={() => onOpenRequest()}
            >
              我要领用
            </Button>
            <Button size="large" icon={<ScanLine size={17} />} onClick={onOpenScanRequest}>
              扫码领用 / 借用
            </Button>
          </>
        }
        aside={
          <div className="operations-hero__aside-card">
            <span>当前未处理任务</span>
            <strong>
              {(summary?.pending_sign ?? 0) +
                (summary?.due_soon ?? 0) +
                (summary?.due_today ?? 0) +
                (summary?.overdue ?? 0)}
            </strong>
            <small>待签收、即将到期、今日到期和已逾期</small>
          </div>
        }
      />

      <OperationsMetrics
        items={[
          {
            label: '待我签收',
            value: summary?.pending_sign ?? 0,
            hint: '管理员已发放',
            tone: 'blue',
          },
          { label: '即将到期', value: summary?.due_soon ?? 0, hint: '7 天内应归还', tone: 'amber' },
          {
            label: '已经逾期',
            value: summary?.overdue ?? 0,
            hint: '请尽快发起退库',
            tone: (summary?.overdue ?? 0) > 0 ? 'red' : 'slate',
          },
          {
            label: '退库处理中',
            value: (summary?.return_processing ?? 0) + (summary?.pending_return_inspection ?? 0),
            hint: '含待管理员验收',
            tone: 'amber',
          },
          {
            label: '我的在用资产',
            value: summary?.my_in_use ?? 0,
            hint: '仅统计个人领用',
            tone: 'green',
          },
          {
            label: '我的借用资产',
            value: summary?.my_borrowed ?? 0,
            hint: '独立归还周期',
            tone: 'blue',
          },
        ]}
      />

      <GlassPanel>
        <SectionHeading
          eyebrow="MY WORK"
          title="我的业务"
          description="每个视图使用独立接口，筛选、搜索和分页均在服务端完成。"
          action={
            <Button icon={<Plus size={15} />} onClick={() => onOpenRequest()}>
              我要领用
            </Button>
          }
        />
        <div className="employee-task-center__tabs">
          {viewOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              className={view === option.value ? 'is-active' : ''}
              onClick={() => changeView(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="employee-task-center__filters">
          <Input
            allowClear
            prefix={<Search size={15} />}
            placeholder="搜索单号、资产编号或名称"
            value={keyword}
            onChange={(event) => {
              setKeyword(event.target.value)
              resetPage()
            }}
          />
          <Select
            allowClear
            placeholder="全部状态"
            value={status}
            onChange={(value) => {
              setStatus(value)
              resetPage()
            }}
            options={(isAssetView(view)
              ? Object.entries(returnMeta)
              : Object.entries(statusMeta)
            ).map(([value, meta]) => ({ value, label: meta.label }))}
          />
          <DatePicker.RangePicker
            value={dates}
            onChange={(value) => {
              setDates(value)
              resetPage()
            }}
            placeholder={
              isAssetView(view)
                ? ['归还日期开始', '归还日期结束']
                : ['发起日期开始', '发起日期结束']
            }
          />
          <Button
            icon={<RotateCcw size={15} />}
            onClick={() => {
              setKeyword('')
              setStatus(undefined)
              setDates(null)
              resetPage()
            }}
          >
            重置
          </Button>
        </div>

        {loading ? (
          <div className="operations-loading">
            <Spin />
          </div>
        ) : failed ? (
          <StatePanel mode="error" message="任务数据加载失败" />
        ) : isReceivedHandoverView ? (
          receivedHandoversQuery.data?.length ? (
            <div className="operations-table employee-task-center__request-table">
              <div className="operations-table__header">
                <span>交接单</span>
                <span>资产</span>
                <span>交接原因</span>
                <span>状态</span>
                <span>操作</span>
              </div>
              {receivedHandoversQuery.data.map((handover: TransferHandover) => (
                <div key={handover.id} className="operations-table__row">
                  <div className="operations-table__primary">
                    <strong>{handover.handover_no}</strong>
                    <small>{dayjs(handover.created_at).format('YYYY-MM-DD HH:mm')}</small>
                  </div>
                  <span>
                    {handover.items
                      .map((item) => `${item.asset_name} · ${item.asset_code}`)
                      .join('、')}
                  </span>
                  <span>{handover.reason}</span>
                  <StatusPill label="待我签收" tone="amber" />
                  <div className="operations-table__status-actions">
                    <Button
                      size="small"
                      type="primary"
                      loading={receivedHandoverMutation.isPending}
                      onClick={() =>
                        receivedHandoverMutation.mutate({ id: handover.id, action: 'RECEIVE' })
                      }
                    >
                      确认接收
                    </Button>
                    <WorkflowEvidenceUpload
                      businessId={handover.id}
                      businessType="TRANSFER_RECEIPT"
                      documentType="TRANSFER_RECEIPT_PHOTO"
                      assets={handover.items}
                      label="签收证据"
                    />
                    <Button
                      size="small"
                      danger
                      loading={receivedHandoverMutation.isPending}
                      onClick={() => {
                        setHandoverRejectTarget(handover)
                        setHandoverRejectReason('')
                      }}
                    >
                      拒绝
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <StatePanel mode="empty" message="当前没有待接收的资产交接" />
          )
        ) : isAssetView(view) ? (
          assetQuery.data?.items.length ? (
            <div className="operations-table employee-task-center__asset-table">
              <div className="operations-table__header">
                <span>资产</span>
                <span>使用方式</span>
                <span>归还日期</span>
                <span>当前任务</span>
                <span>操作</span>
              </div>
              {assetQuery.data.items.map((asset: WorkbenchAsset) => {
                const meta = returnMeta[asset.return_state]
                return (
                  <div key={asset.id} className="operations-table__row">
                    <div className="operations-table__primary">
                      <strong>{asset.asset_name}</strong>
                      <small>{asset.asset_code}</small>
                    </div>
                    <span>{asset.usage_mode === 'BORROW' ? '借用' : '领用'}</span>
                    <span>
                      {asset.expected_return_at
                        ? dayjs(asset.expected_return_at).format('YYYY-MM-DD HH:mm')
                        : '—'}
                    </span>
                    <div className="operations-table__primary">
                      <StatusPill label={meta.label} tone={meta.tone} />
                      {asset.return_request_reason ? (
                        <small>{asset.return_request_reason}</small>
                      ) : null}
                    </div>
                    <div className="operations-table__status-actions">
                      <Button
                        size="small"
                        type={
                          view === 'pending-return' || view === 'my-borrowed'
                            ? 'primary'
                            : 'default'
                        }
                        onClick={() => onOpenRequest(asset.id)}
                      >
                        发起个人退库
                      </Button>
                      {view === 'my-borrowed' && asset.usage_request_id ? (
                        <Button
                          size="small"
                          onClick={() => {
                            setExtensionTarget(asset)
                            extensionForm.setFieldsValue({
                              requested_expected_return_at: asset.expected_return_at
                                ? dayjs(asset.expected_return_at).add(7, 'day')
                                : dayjs().add(7, 'day'),
                              reason: '',
                            })
                          }}
                        >
                          申请延期
                        </Button>
                      ) : null}
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <StatePanel mode="empty" message="当前视图暂无资产" />
          )
        ) : requestQuery.data?.items.length ? (
          <div className="operations-table employee-task-center__request-table">
            <div className="operations-table__header">
              <span>业务</span>
              <span>资产与单号</span>
              <span>发起 / 目标</span>
              <span>状态</span>
              <span>操作</span>
            </div>
            {requestQuery.data.items.map((record: WorkbenchRequest) => {
              const meta = statusMeta[record.display_status] ?? {
                label: workflowStatusLabel(record.display_status),
                tone: 'slate' as const,
              }
              return (
                <div key={record.id} className="operations-table__row">
                  <strong>{operationTypeLabel(record.operation_type)}</strong>
                  <div className="operations-table__primary">
                    <strong>{assetLabel(record)}</strong>
                    <small>{record.request_no}</small>
                  </div>
                  <div className="operations-table__primary">
                    <span>{record.applicant?.name ?? `用户 #${record.applicant_id}`}</span>
                    <small>
                      {record.target_user
                        ? `发给 ${record.target_user.name ?? `用户 #${record.target_user.id}`}`
                        : '本人发起'}
                    </small>
                  </div>
                  <StatusPill label={meta.label} tone={meta.tone} />
                  <div className="operations-table__status-actions">
                    <Button
                      size="small"
                      onClick={() => {
                        setDetailId(null)
                        navigate(`/workflows?request=${record.id}`)
                      }}
                    >
                      查看进度
                    </Button>
                    {record.display_status === 'PENDING_SIGN' ? (
                      <>
                        <Button
                          size="small"
                          type="primary"
                          icon={<PackageCheck size={13} />}
                          loading={fulfillmentMutation.isPending}
                          onClick={() =>
                            fulfillmentMutation.mutate({ id: record.id, action: 'SIGN' })
                          }
                        >
                          签收
                        </Button>
                        <Button
                          size="small"
                          danger
                          loading={fulfillmentMutation.isPending}
                          onClick={() =>
                            fulfillmentMutation.mutate({ id: record.id, action: 'REFUSE_SIGN' })
                          }
                        >
                          拒收
                        </Button>
                      </>
                    ) : null}
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <StatePanel mode="empty" message="当前筛选下暂无业务" />
        )}

        {(pageData?.total ?? 0) > 0 ? (
          <div className="employee-task-center__pagination">
            <span>
              未处理 {pageData?.pending_count ?? 0} 条，共 {pageData?.total ?? 0} 条
            </span>
            <Pagination
              current={page + 1}
              pageSize={20}
              total={pageData?.total ?? 0}
              showSizeChanger={false}
              onChange={(next) => setPage(next - 1)}
            />
          </div>
        ) : null}
      </GlassPanel>

      <Modal
        open={detailId !== null}
        title="申请详情与时间线"
        width={760}
        footer={null}
        onCancel={() => setDetailId(null)}
      >
        {detailQuery.isLoading ? (
          <div className="operations-loading">
            <Spin />
          </div>
        ) : detailQuery.isError ? (
          <StatePanel mode="error" message="申请详情加载失败" />
        ) : detailQuery.data ? (
          <div className="employee-task-center__detail">
            <div className="employee-task-center__next-step">
              <span>
                当前状态：
                {workflowStatusLabel(detailQuery.data.display_status)}
              </span>
              <strong>下一步：{detailQuery.data.next_step}</strong>
              <small>
                当前等待：
                {detailQuery.data.current_handler?.users
                  .map((item) => item?.name)
                  .filter(Boolean)
                  .join('、') ||
                  (detailQuery.data.current_handler?.role
                    ? workflowHandlerRoleLabel(detailQuery.data.current_handler.role)
                    : '无人处理')}
              </small>
              {detailQuery.data.available_actions.includes('SIGN') ? (
                <WorkflowEvidenceUpload
                  businessId={detailQuery.data.id}
                  businessType="USAGE_SIGN"
                  documentType="SIGN_PHOTO"
                  assets={detailQuery.data.assets}
                  label="签收证据（可选）"
                />
              ) : null}
            </div>
            <Timeline
              items={detailQuery.data.timeline.map((event) => ({
                color:
                  event.status === 'REJECTED'
                    ? 'red'
                    : event.status === 'CURRENT'
                      ? 'blue'
                      : 'green',
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
                        审批结果：{event.approval_result === 'APPROVE' ? '通过' : '拒绝'}
                      </small>
                    ) : null}
                    {event.rejection_reason ? (
                      <small>拒绝原因：{event.rejection_reason}</small>
                    ) : null}
                    {event.attachments.length ? (
                      <Space wrap size={[4, 4]}>
                        <small>履约证据：</small>
                        {event.attachments.map((attachment) => (
                          <Button
                            key={attachment.id}
                            type="link"
                            size="small"
                            icon={<Download size={12} />}
                            onClick={() =>
                              void downloadEvidence(attachment.id, attachment.original_name)
                            }
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
        ) : null}
      </Modal>
      <Modal
        open={handoverRejectTarget !== null}
        title={
          handoverRejectTarget
            ? `拒绝资产交接 · ${handoverRejectTarget.handover_no}`
            : '拒绝资产交接'
        }
        className="operations-glass-modal"
        okText="确认拒绝"
        cancelText="取消"
        confirmLoading={receivedHandoverMutation.isPending}
        onCancel={() => {
          setHandoverRejectTarget(null)
          setHandoverRejectReason('')
        }}
        onOk={() => {
          if (!handoverRejectTarget || !handoverRejectReason.trim()) {
            void message.error('请填写拒绝原因')
            return
          }
          receivedHandoverMutation.mutate(
            { id: handoverRejectTarget.id, action: 'REJECT', reason: handoverRejectReason.trim() },
            {
              onSuccess: () => {
                setHandoverRejectTarget(null)
                setHandoverRejectReason('')
              },
            },
          )
        }}
        destroyOnHidden
      >
        <Input.TextArea
          rows={4}
          maxLength={500}
          showCount
          value={handoverRejectReason}
          onChange={(event) => setHandoverRejectReason(event.target.value)}
          placeholder="请说明资产状态、配件或交接信息存在的问题"
        />
        <p className="operations-modal-note">
          拒绝后资产不会变更归属，管理员需要核对后重新发起交接。
        </p>
      </Modal>
      <Modal
        open={extensionTarget !== null}
        title={extensionTarget ? `申请借用延期 · ${extensionTarget.asset_code}` : '申请借用延期'}
        className="operations-glass-modal"
        okText="提交延期申请"
        cancelText="取消"
        confirmLoading={extensionMutation.isPending}
        onCancel={() => {
          setExtensionTarget(null)
          extensionForm.resetFields()
        }}
        onOk={() => extensionForm.submit()}
        destroyOnHidden
      >
        <Form
          form={extensionForm}
          layout="vertical"
          onFinish={(values) => extensionMutation.mutate(values)}
        >
          <Form.Item label="当前归还时间">
            <Input
              value={
                extensionTarget?.expected_return_at
                  ? dayjs(extensionTarget.expected_return_at).format('YYYY-MM-DD HH:mm')
                  : '—'
              }
              disabled
            />
          </Form.Item>
          <Form.Item
            name="requested_expected_return_at"
            label="延期至"
            rules={[{ required: true, message: '请选择新的归还时间' }]}
          >
            <DatePicker
              showTime
              style={{ width: '100%' }}
              disabledDate={(date) =>
                Boolean(
                  extensionTarget?.expected_return_at &&
                  !date.isAfter(dayjs(extensionTarget.expected_return_at), 'day'),
                )
              }
            />
          </Form.Item>
          <Form.Item
            name="reason"
            label="延期原因"
            rules={[{ required: true, min: 2, message: '请填写延期原因' }]}
          >
            <Input.TextArea rows={4} maxLength={500} showCount placeholder="请说明延期使用的原因" />
          </Form.Item>
          {extensionQuery.data?.length ? (
            <div className="operations-modal-note">
              历史延期：
              {extensionQuery.data
                .map(
                  (item) =>
                    `${item.status === 'APPROVED' ? '已通过' : item.status === 'REJECTED' ? '已拒绝' : '审批中'}（${dayjs(item.requested_expected_return_at).format('YYYY-MM-DD HH:mm')}）`,
                )
                .join('、')}
            </div>
          ) : null}
        </Form>
      </Modal>
    </div>
  )
}
