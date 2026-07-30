import { Button, Input, Modal, Segmented, Spin, message } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ClipboardCheck, Clock3, FileCheck2, ShieldCheck, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { operationApi, type ApprovalTask } from '@/api/operations'
import StatePanel from '@/components/ui/StatePanel'
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
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ['approval-tasks', 'my'],
    queryFn: operationApi.myTasks,
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

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow="APPROVAL CENTER"
        title="把关键决定，放在清晰的上下文里"
        description="审批收件箱已连接后端，可以直接通过或退回当前待办任务。"
        icon={ClipboardCheck}
        tone="violet"
        actions={
          <Button type="primary" size="large" icon={<FileCheck2 size={18} />} disabled>
            批量审批暂未开放
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
                        任务编号 #{task.id} · 流程 #{task.operation_request_id}
                      </span>
                      <div style={{ marginTop: 10 }}>
                        <StatusPill label={status.label} tone={status.tone} />
                      </div>
                    </div>
                    {task.status === 'PENDING' ? (
                      <div className="operations-approval__actions">
                        <Button
                          size="small"
                          icon={<X size={14} />}
                          loading={isRejecting}
                          disabled={approveMutation.isPending}
                          onClick={() => setRejectTask(task)}
                        >
                          退回
                        </Button>
                        <Button
                          type="primary"
                          size="small"
                          icon={<Check size={14} />}
                          loading={isApproving}
                          disabled={rejectMutation.isPending}
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
                <strong>退回必须填写原因</strong>
                <span>意见会进入流程审批轨迹，便于申请人补充资料</span>
              </div>
            </div>
          </div>
        </GlassPanel>
      </div>

      <Modal
        title={`退回 ${rejectTask?.request_no ?? ''}`}
        open={Boolean(rejectTask)}
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
    </div>
  )
}
