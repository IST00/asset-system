import { Button, Segmented, Spin, message } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, ClipboardCheck, PackageCheck, RefreshCw, ScanLine, ShieldAlert } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { inventoryApi } from '@/api/inventory'
import { workbenchApi } from '@/api/workbench'
import { operationApi } from '@/api/operations'
import { notificationsApi, type UserNotification } from '@/api/notifications'
import StatePanel from '@/components/ui/StatePanel'
import { formatBeijingDateTime } from '@/utils/dateTime'
import type { Tone } from './data'
import { GlassPanel, OperationsHero, SectionHeading, StatusPill } from './OperationsUI'

interface TodoItem {
  id: string
  title: string
  detail: string
  meta: string
  type: '审批待办' | '盘点待办' | '盘点异常' | '资产待处理'
  tone: Tone
  target: '/approvals' | '/inventory' | '/workflows'
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
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ['todo-center'],
    queryFn: async () => {
      const [approvalTasks, inventoryTasks, workbenchSummary, notifications, unreadCount] =
        await Promise.all([
          operationApi.myTasks(),
          inventoryApi.tasks(),
          workbenchApi.summary(),
          notificationsApi.page({ page: 0, size: 50 }),
          notificationsApi.unreadCount(),
        ])
      return {
        approvalTasks,
        inventoryTasks: inventoryTasks.items,
        workbenchSummary,
        notifications: notifications.items,
        unreadCount,
      }
    },
    refetchInterval: 60_000,
  })

  const markReadMutation = useMutation({
    mutationFn: (id: number) => notificationsApi.markRead(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['todo-center'] })
      await queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })
  const markAllReadMutation = useMutation({
    mutationFn: notificationsApi.markAllRead,
    onSuccess: async () => {
      await message.success('全部通知已标为已读')
      await queryClient.invalidateQueries({ queryKey: ['todo-center'] })
      await queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
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
    const summary = query.data?.workbenchSummary
    const assetItems: TodoItem[] = []
    if (summary?.pending_issue) {
      assetItems.push({
        id: 'workbench-pending-issue',
        title: `有 ${summary.pending_issue} 项资产待管理员发放`,
        detail: '审批通过后仍需选择具体资产并完成发放。',
        meta: '资产任务中心',
        type: '资产待处理',
        tone: 'amber',
        target: '/workflows',
        icon: PackageCheck,
      })
    }
    if (summary?.pending_return_inspection) {
      assetItems.push({
        id: 'workbench-pending-inspection',
        title: `有 ${summary.pending_return_inspection} 项退库待管理员验收`,
        detail: '请验收资产并选择退库后公司、使用公司、区域和存放地点。',
        meta: '资产任务中心',
        type: '资产待处理',
        tone: 'amber',
        target: '/workflows',
        icon: PackageCheck,
      })
    }
    if (summary?.pending_sign) {
      assetItems.push({
        id: 'workbench-pending-sign',
        title: `有 ${summary.pending_sign} 项资产待本人签收`,
        detail: '管理员已发放资产，请在工作台确认收到或拒收。',
        meta: '资产任务中心',
        type: '资产待处理',
        tone: 'blue',
        target: '/workflows',
        icon: PackageCheck,
      })
    }
    if (summary?.overdue) {
      assetItems.push({
        id: 'workbench-overdue',
        title: `有 ${summary.overdue} 项借用资产已逾期`,
        detail: '请尽快发起退库，或联系管理员确认归还安排。',
        meta: '资产任务中心',
        type: '资产待处理',
        tone: 'red',
        target: '/workflows',
        icon: ShieldAlert,
      })
    }
    const notificationItems: TodoItem[] = (query.data?.notifications ?? []).map(
      (notification: UserNotification) => ({
        id: `notification-${notification.id}`,
        title: notification.title,
        detail: notification.content,
        meta: notification.read_at ? '系统通知 · 已读' : '系统通知 · 未读',
        type: '资产待处理',
        tone: notification.notification_type.includes('OVERDUE') ? 'red' : 'blue',
        target: notification.notification_type === 'APPROVAL' ? '/approvals' : '/workflows',
        icon: Bell,
      }),
    )
    return [...approvalItems, ...inventoryItems, ...assetItems, ...notificationItems]
  }, [query.data])

  const visibleItems = items.filter((item) => filter === '全部' || item.type === filter)
  const urgentCount = items.filter((item) => item.tone === 'red').length

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow="TODO CENTER"
        title="只呈现真实待办，不再用演示消息制造繁忙"
        description="本页实时汇总当前账号的审批、盘点和资产履约待办；点击后进入对应业务页面处理。当前仍是实时任务视图，不伪造未读消息。"
        icon={Bell}
        tone="blue"
        actions={
          <div className="operations-toolbar">
            <Button
              type="primary"
              size="large"
              icon={<RefreshCw size={17} />}
              loading={query.isFetching}
              onClick={() => void query.refetch()}
            >
              刷新待办
            </Button>
            <Button
              size="large"
              disabled={!query.data?.unreadCount}
              loading={markAllReadMutation.isPending}
              onClick={() => markAllReadMutation.mutate()}
            >
              全部标为已读{query.data?.unreadCount ? `（${query.data.unreadCount}）` : ''}
            </Button>
          </div>
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
              options={['全部', '审批待办', '资产待处理', '盘点待办', '盘点异常']}
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
            message="待办加载失败，请确认审批、盘点和资产任务接口可访问"
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
                  onClick={() => {
                    if (item.id.startsWith('notification-')) {
                      const notificationId = Number(item.id.replace('notification-', ''))
                      if (Number.isInteger(notificationId)) markReadMutation.mutate(notificationId)
                    }
                    navigate(item.target)
                  }}
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
