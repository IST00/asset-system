import { useMemo, useState } from 'react'
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
  Spin,
  message,
} from 'antd'
import dayjs from 'dayjs'
import {
  Bell,
  ArrowLeftRight,
  ArrowUpRight,
  PackageCheck,
  Plus,
  Trash2,
  Wrench,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { assetManagementApi } from '@/api/assetManagement'
import {
  assetUsageReturnApi,
  type AssetUsageReturnAction,
  type AssetUsageReturnSubmission,
} from '@/api/assetUsageReturn'
import { listAssets, loadAssetReferences } from '@/api/assets'
import { operationApi, type OperationRequest } from '@/api/operations'
import StatePanel from '@/components/ui/StatePanel'
import type { TreeItem } from '@/api/administration'
import type { AssetSummary } from '@/features/assets/types'
import { useAuthStore } from '@/store/auth'
import type { Tone } from './data'
import ReturnConfirmModal from './ReturnConfirmModal'
import UsageReturnModal from './UsageReturnModal'
import {
  GlassPanel,
  OperationsHero,
  OperationsMetrics,
  SectionHeading,
  StatusPill,
} from './OperationsUI'

type LifecycleAction = 'TRANSFER' | 'REPAIR_START' | 'REPAIR_COMPLETE' | 'SCRAP'

interface LifecycleFormValues {
  asset_ids: number[]
  location_id?: number
  manager_id?: number
  holder_user_id?: number
  vendor?: string
  estimated_cost?: number
  actual_cost?: number
  scrap_date?: dayjs.Dayjs
  scrap_amount?: number
  child_action?: 'BLOCK' | 'DETACH' | 'SCRAP'
  reason: string
}

const operationTypeLabels: Record<string, string> = {
  STOCK_IN: '资产入库',
  PERSONAL_USE: '个人领用',
  PUBLIC_USE: '公共领用',
  PERSONAL_RETURN: '个人退库',
  PUBLIC_RETURN: '公共退库',
  TRANSFER: '资产调拨',
  REPAIR_START: '发起维修',
  REPAIR_COMPLETE: '维修完成',
  SCRAP: '资产报废',
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
    description: '发起个人或公共资产领用、退库，并完成个人退库验收',
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
]

function operationStatus(record: OperationRequest): { label: string; tone: Tone } {
  if (record.approval_status === 'REJECTED') return { label: '已拒绝', tone: 'red' }
  if (record.approval_status === 'WITHDRAWN') return { label: '已撤回', tone: 'slate' }
  if (record.approval_status === 'PENDING') return { label: '审批中', tone: 'blue' }
  if (record.execution_status === 'FAILED') return { label: '执行失败', tone: 'red' }
  if (record.execution_status === 'PROCESSING') return { label: '执行中', tone: 'amber' }
  if (record.execution_status === 'SUCCESS') return { label: '已完成', tone: 'green' }
  if (record.execution_status === 'TERMINATED') return { label: '已终止', tone: 'slate' }
  return { label: '待执行', tone: 'cyan' }
}

function operationAssetLabel(record: OperationRequest): string {
  const first = record.assets[0]
  if (!first) return '未关联资产'
  const extra = record.assets.length > 1 ? ` 等 ${record.assets.length} 件` : ''
  return `${first.asset_name} · ${first.asset_code}${extra}`
}

function actionAllowed(asset: AssetSummary, action: LifecycleAction): boolean {
  if (action === 'REPAIR_COMPLETE') return asset.status === 'REPAIRING'
  if (action === 'REPAIR_START' || action === 'TRANSFER') {
    return asset.status === 'IDLE' || asset.status === 'IN_USE'
  }
  return asset.status !== 'SCRAPPED'
}

export default function Workflows() {
  const [filter, setFilter] = useState('全部')
  const [action, setAction] = useState<LifecycleAction | null>(null)
  const [usageReturnOpen, setUsageReturnOpen] = useState(false)
  const [returnConfirmTarget, setReturnConfirmTarget] = useState<OperationRequest | null>(null)
  const [remindTarget, setRemindTarget] = useState<OperationRequest | null>(null)
  const [remindReason, setRemindReason] = useState('')
  const [form] = Form.useForm<LifecycleFormValues>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const currentUserId = useAuthStore((state) => state.user?.id)
  const permissions = useAuthStore((state) => state.user?.permissions)
  const canManageUsage = permissions?.includes('asset:usage:manage') ?? false
  const canSelfReturn = permissions?.includes('asset:return:self') ?? false
  const availableUsageReturnActions = useMemo<AssetUsageReturnAction[]>(() => {
    const actions: AssetUsageReturnAction[] = []
    if (canManageUsage) actions.push('PERSONAL_USE', 'PUBLIC_USE', 'PUBLIC_RETURN')
    if (canSelfReturn) actions.push('PERSONAL_RETURN')
    return actions
  }, [canManageUsage, canSelfReturn])
  const query = useQuery({
    queryKey: ['operation-requests'],
    queryFn: () => operationApi.list(0, 50),
  })
  const assetQuery = useQuery({
    queryKey: ['assets', 'workflow-picker'],
    queryFn: () => listAssets({ page: 1, size: 100 }),
  })
  const referenceQuery = useQuery({
    queryKey: ['asset-form', 'references'],
    queryFn: loadAssetReferences,
    staleTime: 60_000,
  })
  const publicObjectQuery = useQuery({
    queryKey: ['public-usage-objects', 'enabled'],
    queryFn: () => assetManagementApi.publicObjects(false),
    staleTime: 60_000,
  })
  const records = useMemo(() => query.data?.items ?? [], [query.data])
  const assets = useMemo(() => assetQuery.data?.records ?? [], [assetQuery.data])
  const filteredRecords = useMemo(() => {
    if (filter === '处理中') {
      return records.filter((record) => {
        const status = operationStatus(record).label
        return !['已完成', '已拒绝', '已撤回', '已终止'].includes(status)
      })
    }
    if (filter === '我发起的') {
      return records.filter((record) => record.applicant_id === currentUserId)
    }
    return records
  }, [currentUserId, filter, records])

  const pendingApproval = records.filter((record) => record.approval_status === 'PENDING').length
  const processing = records.filter((record) => record.execution_status === 'PROCESSING').length
  const completed = records.filter((record) => record.execution_status === 'SUCCESS').length
  const failed = records.filter((record) => record.execution_status === 'FAILED').length

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
      setUsageReturnOpen(false)
      const statusText = result.execution_status === 'SUCCESS' ? '已完成办理' : '已提交真实申请'
      await message.success(`${statusText}，单号 ${result.request_no}`)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['operation-requests'] }),
        queryClient.invalidateQueries({ queryKey: ['assets'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['todo-center'] }),
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
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['todo-center'] }),
      ])
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
      if (values.scrap_amount === undefined) throw new Error('请填写报废回收金额')
      return assetManagementApi.scrap({
        items,
        scrap_date: (values.scrap_date ?? dayjs()).format('YYYY-MM-DD'),
        scrap_amount: values.scrap_amount.toFixed(2),
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
      scrap_date: dayjs(),
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
    return references
      ? flatten(references.locations)
          .filter((item) => item.status !== 'DISABLED')
          .map((item) => ({ label: `${item.name} · ${item.code}`, value: item.id }))
      : []
  }, [references])

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
              type="primary"
              size="large"
              icon={<Plus size={17} />}
              onClick={() => navigate('/assets/new')}
            >
              发起入库申请
            </Button>
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
                    else if (cardAction) openAction(cardAction)
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
          title="最近审批流程"
          description="显示后端返回的最近 50 条审批操作单；直接业务命令可在资产详情的生命周期中查看。"
          action={
            <Segmented
              value={filter}
              options={['全部', '处理中', '我发起的']}
              onChange={(value) => setFilter(String(value))}
            />
          }
        />
        {query.isLoading ? (
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
                  <strong>
                    {operationTypeLabels[record.operation_type] ?? record.operation_type}
                  </strong>
                  <div className="operations-table__primary">
                    <strong>{operationAssetLabel(record)}</strong>
                    <small>{record.request_no}</small>
                  </div>
                  <span>
                    {record.applicant_id === currentUserId ? '我' : `用户 #${record.applicant_id}`}
                  </span>
                  <span>
                    {record.approval_status} / {record.execution_status}
                  </span>
                  <div className="operations-table__status-actions">
                    <StatusPill label={status.label} tone={status.tone} />
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
                    record.operation_type === 'PERSONAL_RETURN' &&
                    record.approval_status === 'APPROVED' &&
                    record.execution_status === 'NOT_STARTED' ? (
                      <Button
                        size="small"
                        type="primary"
                        icon={<PackageCheck size={13} />}
                        onClick={() => setReturnConfirmTarget(record)}
                      >
                        验收退库
                      </Button>
                    ) : null}
                    {record.applicant_id === currentUserId &&
                    record.approval_status === 'PENDING' ? (
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
        assets={assets}
        users={(referenceQuery.data?.managers ?? [])
          .filter((user) => user.enabled)
          .map((user) => ({ label: user.name, value: user.id }))}
        publicObjects={publicObjectQuery.data ?? []}
        locations={locationOptions}
        availableActions={availableUsageReturnActions}
        currentUserId={currentUserId}
        loading={usageReturnMutation.isPending}
        onCancel={() => setUsageReturnOpen(false)}
        onSubmit={(submission) => usageReturnMutation.mutate(submission)}
      />

      <ReturnConfirmModal
        target={returnConfirmTarget}
        locations={locationOptions}
        loading={returnConfirmMutation.isPending}
        onCancel={() => setReturnConfirmTarget(null)}
        onSubmit={(payload) => {
          if (!returnConfirmTarget) return
          returnConfirmMutation.mutate({ operationId: returnConfirmTarget.id, payload })
        }}
      />

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
              <Form.Item name="scrap_date" label="报废日期" rules={[{ required: true }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item
                name="scrap_amount"
                label="回收金额"
                rules={[{ required: true, message: '请填写回收金额，可填写 0' }]}
              >
                <InputNumber min={0} precision={2} prefix="¥" style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="child_action" label="主资产的附属资产处理">
                <Select
                  options={[
                    { label: '存在附属资产时阻止报废', value: 'BLOCK' },
                    { label: '解除关系后仅报废主资产', value: 'DETACH' },
                    { label: '主附资产一起报废', value: 'SCRAP' },
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
    </div>
  )
}
