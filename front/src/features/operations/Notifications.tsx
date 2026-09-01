import { Button, Segmented, Spin } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { Bell, ClipboardCheck, RefreshCw, ScanLine, ShieldAlert } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { inventoryApi } from '@/api/inventory'
import { operationApi } from '@/api/operations'
import StatePanel from '@/components/ui/StatePanel'
import { formatBeijingDateTime } from '@/utils/dateTime'
import type { Tone } from './data'
import { GlassPanel, OperationsHero, SectionHeading, StatusPill } from './OperationsUI'

interface TodoItem {
  id: string
  title: string
  detail: string
  meta: string
  type: '审批待办' | '盘点待办' | '盘点异常'
  tone: Tone
  target: '/approvals' | '/inventory'
  icon: typeof ClipboardCheck
}

const operationLabels: Record<string, string> = {
  STOCK_IN: '资产入库',
  ASSET_USAGE: '资产领用',
  ASSET_RETURN: '资产退库',
  TRANSFER: '资产转移',
  REPAIR: '资产维修',
  SCRAP: '资产报废',
}

export default function Notifications() {
  const [filter, setFilter] = useState('全部')
  const navigate = useNavigate()
  const query = useQuery({
    queryKey: ['todo-center'],
    queryFn: async () => {
      const [approvalTasks, inventoryTasks] = await Promise.all([
        operationApi.myTasks(),
        inventoryApi.tasks(),
      ])
      return { approvalTasks, inventoryTasks: inventoryTasks.items }
    },
    refetchInterval: 60_000,
  })

  const items = useMemo<TodoItem[]>(() => {
    const approvalItems: TodoItem[] = (query.data?.approvalTasks ?? []).map((task) => ({
      id: `approval-${task.id}`,
      title: `${operationLabels[task.operation_type] ?? task.operation_type}等待审批`,
      detail: `单号 ${task.request_no}，当前第 ${task.level_no} 级审批。`,
      meta: '来自实时审批任务',
      type: '审批待办',
      tone: 'violet',
      target: '/approvals',
      icon: ClipboardCheck,
    }))
    const inventoryItems: TodoItem[] = (query.data?.inventoryTasks ?? [])
      .filter((task) => !['COMPLETED', 'CANCELLED'].includes(task.status))
      .flatMap<TodoItem>((task) => {
        const result: TodoItem[] = []
        if (task.counts.pending > 0 && ['IN_PROGRESS', 'OVERDUE'].includes(task.status)) {
          result.push({
            id: `inventory-pending-${task.id}`,
            title: `${task.name}仍有 ${task.counts.pending} 件待盘点`,
            detail: `任务 ${task.task_no}，截止时间 ${formatBeijingDateTime(task.deadline_at)}。`,
            meta: task.status === 'OVERDUE' ? '已超过软截止时间' : `当前进度 ${task.progress}%`,
            type: '盘点待办',
            tone: task.status === 'OVERDUE' ? 'red' : 'amber',
            target: '/inventory',
            icon: ScanLine,
          })
        }
        if (
          task.counts.exceptions > 0 &&
          ['REVIEWING', 'IN_PROGRESS', 'OVERDUE'].includes(task.status)
        ) {
          result.push({
            id: `inventory-exception-${task.id}`,
            title: `${task.name}有 ${task.counts.exceptions} 条异常待处理`,
            detail: `盘亏、地点差异或未提交结果需要盘点管理员复核。`,
            meta: `任务 ${task.task_no}`,
            type: '盘点异常',
            tone: 'red',
            target: '/inventory',
            icon: ShieldAlert,
          })
        }
        return result
      })
    return [...approvalItems, ...inventoryItems]
  }, [query.data])

  const visibleItems = items.filter((item) => filter === '全部' || item.type === filter)
  const urgentCount = items.filter((item) => item.tone === 'red').length

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow="TODO CENTER"
        title="只呈现真实待办，不再用演示消息制造繁忙"
        description="本页实时汇总当前账号的审批任务与盘点事项。系统尚未建设持久化消息收件箱，因此不提供假的未读和已读状态。"
        icon={Bell}
        tone="blue"
        actions={
          <Button
            type="primary"
            size="large"
            icon={<RefreshCw size={17} />}
            loading={query.isFetching}
            onClick={() => void query.refetch()}
          >
            刷新待办
          </Button>
        }
        aside={
          <div className="operations-hero__aside-card">
            <span>当前待办</span>
            <strong>{items.length}</strong>
            <small>
              {urgentCount ? `${urgentCount} 项异常或逾期需要优先处理` : '当前没有异常或逾期事项'}
            </small>
          </div>
        }
      />

      <GlassPanel>
        <SectionHeading
          eyebrow="LIVE TASKS"
          title="实时待办"
          description="点击条目进入对应业务页面处理，完成后列表会随接口数据消失。"
          action={
            <Segmented
              value={filter}
              options={['全部', '审批待办', '盘点待办', '盘点异常']}
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
            message="待办加载失败，请确认审批和盘点接口可访问"
            retryLabel="重新加载"
            onRetry={() => void query.refetch()}
          />
        ) : visibleItems.length ? (
          <div className="operations-approval-list">
            {visibleItems.map((item) => {
              const Icon = item.icon
              return (
                <button
                  key={item.id}
                  type="button"
                  className={`operations-approval operations-tone--${item.tone}`}
                  onClick={() => navigate(item.target)}
                >
                  <span className="operations-approval__icon">
                    <Icon size={20} />
                  </span>
                  <div className="operations-approval__content">
                    <strong>{item.title}</strong>
                    <span className="operations-approval__summary">{item.detail}</span>
                    <span>{item.meta}</span>
                  </div>
                  <StatusPill label={item.type} tone={item.tone} />
                </button>
              )
            })}
          </div>
        ) : (
          <div className="operations-empty-note">当前筛选下没有待办事项</div>
        )}
      </GlassPanel>
    </div>
  )
}
