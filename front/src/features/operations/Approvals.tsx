import { Button, Input, Modal, Segmented, Select, Spin, message } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeftRight,
  Check,
  ClipboardCheck,
  Clock3,
  RefreshCw,
  ShieldCheck,
  X,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { operationApi, type ApprovalTask } from '@/api/operations'
import StatePanel from '@/components/ui/StatePanel'
import { useAuthStore } from '@/store/auth'
import type { Tone } from './data'
import {
  GlassPanel,
  OperationsHero,
  OperationsMetrics,
  SectionHeading,
  StatusPill,
} from './OperationsUI'

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

function taskStatus(status: string): { label: string; tone: Tone } {
  if (status === 'PENDING') return { label: '待我审批', tone: 'violet' }
  if (status === 'APPROVED') return { label: '已通过', tone: 'green' }
  if (status === 'REJECTED') return { label: '已拒绝', tone: 'red' }
  if (status === 'WITHDRAWN') return { label: '已撤回', tone: 'slate' }
  return { label: '等待前序审批', tone: 'amber' }
}

export default function Approvals() {
  const [filter, setFilter] = useState('待我审批')
  const [rejectTask, setRejectTask] = useState<ApprovalTask | null>(null)
  const [rejectOpinion, setRejectOpinion] = useState('')
  const [transferTask, setTransferTask] = useState<ApprovalTask | null>(null)
  const [toApproverId, setToApproverId] = useState<number | null>(null)
  const [transferReason, setTransferReason] = useState('')
  const permissions = useAuthStore((state) => state.user?.permissions ?? [])
  const canTransfer = permissions.includes('approval:task:transfer')
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ['approval-tasks', 'my'],
    queryFn: operationApi.myTasks,
  })
  const candidateQuery = useQuery({
    queryKey: ['approval-transfer-candidates', transferTask?.id],
    queryFn: () => operationApi.transferCandidates(transferTask?.id ?? 0),
    enabled: transferTask !== null,
  })
  const tasks = useMemo(() => query.data ?? [], [query.data])
  const filteredTasks = useMemo(() => {
    if (filter === '全部') return tasks
    if (filter === '已处理')
      return tasks.filter((task) => ['APPROVED', 'REJECTED', 'WITHDRAWN'].includes(task.status))
    return tasks.filter((task) => task.status === 'PENDING')
  }, [filter, tasks])

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['approval-tasks', 'my'] }),
      queryClient.invalidateQueries({ queryKey: ['operation-requests'] }),
    ])
  }
  const approveMutation = useMutation({
    mutationFn: (taskId: number) => operationApi.approve(taskId, '同意'),
    onSuccess: async () => {
      void message.success('审批已通过')
      await refresh()
    },
    onError: (error: Error) => void message.error(error.message),
  })
  const rejectMutation = useMutation({
    mutationFn: ({ taskId, opinion }: { taskId: number; opinion: string }) =>
      operationApi.reject(taskId, opinion),
    onSuccess: async () => {
      setRejectTask(null)
      setRejectOpinion('')
      void message.success('审批已退回')
      await refresh()
    },
    onError: (error: Error) => void message.error(error.message),
  })
  const transferMutation = useMutation({
    mutationFn: ({
      task,
      approverId,
      reason,
    }: {
      task: ApprovalTask
      approverId: number
      reason: string
    }) => operationApi.transfer(task.id, approverId, task.version, reason),
    onSuccess: async () => {
      setTransferTask(null)
      setToApproverId(null)
      setTransferReason('')
      void message.success('审批任务已转交')
      await refresh()
    },
    onError: (error: Error) => void message.error(error.message),
  })

  const pendingCount = tasks.filter((task) => task.status === 'PENDING').length
  const processedCount = tasks.filter((task) =>
    ['APPROVED', 'REJECTED', 'WITHDRAWN'].includes(task.status),
  ).length
  const waitingCount = tasks.filter((task) => task.status === 'WAITING').length
  const approvedCount = tasks.filter((task) => task.status === 'APPROVED').length
  const processedDecisionCount = tasks.filter((task) =>
    ['APPROVED', 'REJECTED'].includes(task.status),
  ).length
  const approvalRate = processedDecisionCount
    ? `${Math.round((approvedCount / processedDecisionCount) * 100)}%`
    : '—'

  const submitReject = () => {
    const opinion = rejectOpinion.trim()
    if (!rejectTask || !opinion) {
      void message.warning('请填写退回原因')
      return
    }
    rejectMutation.mutate({ taskId: rejectTask.id, opinion })
  }

  const submitTransfer = () => {
    const reason = transferReason.trim()
    if (!transferTask || !toApproverId || reason.length < 2) {
      void message.warning('请选择新审批人并填写转交原因')
      return
    }
    transferMutation.mutate({ task: transferTask, approverId: toApproverId, reason })
  }

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow="APPROVAL CENTER"
        title="把关键决定，放在清晰的上下文里"
        description="审批收件箱已连接后端，支持通过、退回和受控转交；所有转交都会保留前后审批人与原因。"
        icon={ClipboardCheck}
        tone="violet"
        actions={
          <Button
            type="primary"
            size="large"
            icon={<RefreshCw size={18} />}
            loading={query.isFetching}
            onClick={() => void refresh()}
          >
            刷新审批待办
          </Button>
        }
        aside={
          <div className="operations-hero__aside-card">
            <span>我的待办</span>
            <strong>{pendingCount}</strong>
            <small>来自后端审批任务接口</small>
          </div>
        }
      />

      <OperationsMetrics
        items={[
          { label: '待我审批', value: pendingCount, hint: '可以立即处理', tone: 'violet' },
          { label: '已处理', value: processedCount, hint: '当前账号历史任务', tone: 'green' },
          { label: '等待前序审批', value: waitingCount, hint: '暂不可操作', tone: 'amber' },
          { label: '审批通过率', value: approvalRate, hint: '按已决任务计算', tone: 'blue' },
        ]}
      />

      <div className="operations-split">
        <GlassPanel>
          <SectionHeading
            eyebrow="INBOX"
            title="审批收件箱"
            description="只有状态为“待我审批”的任务会显示处理按钮。"
            action={
              <Segmented
                value={filter}
                options={['待我审批', '已处理', '全部']}
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
              message="审批任务加载失败"
              retryLabel="重新加载"
              onRetry={() => void query.refetch()}
            />
          ) : filteredTasks.length ? (
            <div className="operations-approval-list">
              {filteredTasks.map((task) => {
                const status = taskStatus(task.status)
                const isApproving =
                  approveMutation.isPending && approveMutation.variables === task.id
                const isRejecting =
                  rejectMutation.isPending && rejectMutation.variables?.taskId === task.id
                return (
                  <article
                    key={task.id}
                    className={`operations-approval operations-tone--${status.tone}`}
                  >
                    <span className="operations-approval__icon">
                      <ClipboardCheck aria-hidden="true" size={20} />
                    </span>
                    <div className="operations-approval__content">
                      <strong>
                        {operationTypeLabels[task.operation_type] ?? task.operation_type}
                      </strong>
                      <span>
                        {task.request_no} · 第 {task.level_no} 级审批
                      </span>
                      <span className="operations-approval__summary">
                        任务编号 #{task.id} · 流程 #{task.operation_request_id} · 版本{' '}
                        {task.version}
                      </span>
                      <div style={{ marginTop: 10 }}>
                        <StatusPill label={status.label} tone={status.tone} />
                      </div>
                    </div>
                    {task.status === 'PENDING' ? (
                      <div className="operations-approval__actions">
                        {canTransfer ? (
                          <Button
                            size="small"
                            icon={<ArrowLeftRight size={14} />}
                            disabled={approveMutation.isPending || rejectMutation.isPending}
                            onClick={() => {
                              setTransferTask(task)
                              setToApproverId(null)
                              setTransferReason('')
                            }}
                          >
                            转交
                          </Button>
                        ) : null}
                        <Button
                          size="small"
                          icon={<X size={14} />}
                          loading={isRejecting}
                          disabled={approveMutation.isPending || transferMutation.isPending}
                          onClick={() => setRejectTask(task)}
                        >
                          退回
                        </Button>
                        <Button
                          type="primary"
                          size="small"
                          icon={<Check size={14} />}
                          loading={isApproving}
                          disabled={rejectMutation.isPending || transferMutation.isPending}
                          onClick={() => approveMutation.mutate(task.id)}
                        >
                          通过
                        </Button>
                      </div>
                    ) : null}
                  </article>
                )
              })}
            </div>
          ) : (
            <StatePanel mode="empty" message="当前筛选下暂无审批记录" />
          )}
        </GlassPanel>

        <GlassPanel>
          <SectionHeading
            eyebrow="POLICY"
            title="审批规则"
            description="后端当前执行的审批约束。"
          />
          <div className="operations-settings-list">
            <div className="operations-setting operations-tone--violet">
              <span className="operations-setting__icon">
                <ShieldCheck size={18} />
              </span>
              <div className="operations-setting__content">
                <strong>按审批层级流转</strong>
                <span>前序任务完成后，下一层审批人才可处理</span>
              </div>
            </div>
            <div className="operations-setting operations-tone--amber">
              <span className="operations-setting__icon">
                <Clock3 size={18} />
              </span>
              <div className="operations-setting__content">
                <strong>转交与退回必须填写原因</strong>
                <span>转交校验目标人员权限、数据范围和任务版本，并写入审计</span>
              </div>
            </div>
          </div>
        </GlassPanel>
      </div>

      <Modal
        title={`退回 ${rejectTask?.request_no ?? ''}`}
        open={Boolean(rejectTask)}
        className="operations-glass-modal"
        okText="确认退回"
        cancelText="取消"
        confirmLoading={rejectMutation.isPending}
        onOk={submitReject}
        onCancel={() => {
          setRejectTask(null)
          setRejectOpinion('')
        }}
      >
        <Input.TextArea
          value={rejectOpinion}
          rows={4}
          maxLength={2000}
          showCount
          placeholder="请填写退回原因（必填）"
          onChange={(event) => setRejectOpinion(event.target.value)}
        />
      </Modal>

      <Modal
        title={`转交 ${transferTask?.request_no ?? ''}`}
        open={Boolean(transferTask)}
        className="operations-glass-modal"
        okText="确认转交"
        cancelText="取消"
        confirmLoading={transferMutation.isPending}
        onOk={submitTransfer}
        onCancel={() => {
          setTransferTask(null)
          setToApproverId(null)
          setTransferReason('')
        }}
      >
        <div className="operations-modal-fields">
          <label>
            <span>新审批人</span>
            <Select
              value={toApproverId}
              loading={candidateQuery.isLoading}
              placeholder={candidateQuery.isError ? '候选人加载失败' : '选择具备权限的审批人'}
              notFoundContent={candidateQuery.isLoading ? <Spin size="small" /> : '暂无可转交人员'}
              options={(candidateQuery.data ?? []).map((candidate) => ({
                label: `${candidate.nickname || candidate.username} · ${candidate.username}`,
                value: candidate.id,
              }))}
              onChange={setToApproverId}
            />
          </label>
          <label>
            <span>转交原因</span>
            <Input.TextArea
              value={transferReason}
              rows={4}
              maxLength={500}
              showCount
              placeholder="请说明转交原因（至少 2 个字）"
              onChange={(event) => setTransferReason(event.target.value)}
            />
          </label>
          <p className="operations-modal-note">
            转交后当前任务将从你的待办中移出，新审批人可继续处理；原审批人、目标审批人和原因都会永久留痕。
          </p>
        </div>
      </Modal>
    </div>
  )
}
