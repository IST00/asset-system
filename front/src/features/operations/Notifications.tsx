import { Button, Segmented, message } from 'antd'
import { Bell, CheckCheck, ClipboardCheck, PackageCheck, ScanLine, ShieldAlert } from 'lucide-react'
import { useMemo, useState } from 'react'
import { GlassPanel, OperationsHero, SectionHeading, StatusPill } from './OperationsUI'

const notificationItems = [
  {
    id: 1,
    title: '第三季度全员盘点即将截止',
    detail: '还有 344 件资产未完成盘点，任务将在 2026-07-31 18:00 截止。',
    time: '8 分钟前',
    type: '盘点提醒',
    tone: 'amber' as const,
    icon: ScanLine,
    unread: true,
  },
  {
    id: 2,
    title: '你有新的资产调拨审批',
    detail: '周明远提交了戴尔显示器跨城市调拨申请，需要你确认。',
    time: '24 分钟前',
    type: '审批待办',
    tone: 'violet' as const,
    icon: ClipboardCheck,
    unread: true,
  },
  {
    id: 3,
    title: '资产领用已被员工确认',
    detail: '林小满已确认收到 MacBook Pro 14，资产状态已更新为“在用”。',
    time: '1 小时前',
    type: '流程动态',
    tone: 'green' as const,
    icon: PackageCheck,
    unread: true,
  },
  {
    id: 4,
    title: '导入任务存在 4 条错误数据',
    detail: '第三季度新增资产.xlsx 已完成校验，请下载错误回执后修正。',
    time: '2 小时前',
    type: '数据提醒',
    tone: 'red' as const,
    icon: ShieldAlert,
    unread: false,
  },
  {
    id: 5,
    title: '研发中心专项盘点进度达到 87%',
    detail: '当前已完成 302/346 件资产，仍有 6 条异常需要确认。',
    time: '昨天 17:30',
    type: '盘点动态',
    tone: 'cyan' as const,
    icon: ScanLine,
    unread: false,
  },
]

export default function Notifications() {
  const [filter, setFilter] = useState('全部')
  const [readIds, setReadIds] = useState<number[]>(
    notificationItems.filter((item) => !item.unread).map((item) => item.id),
  )
  const visibleItems = useMemo(
    () =>
      filter === '未读'
        ? notificationItems.filter((item) => !readIds.includes(item.id))
        : notificationItems,
    [filter, readIds],
  )

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow="MESSAGE CENTER"
        title="重要动态，在需要你的时候出现"
        description="通知后端接口尚未建设，当前列表为玻璃风格演示数据，标记已读只在本页面生效。"
        icon={Bell}
        tone="blue"
        actions={
          <Button
            type="primary"
            size="large"
            icon={<CheckCheck size={17} />}
            onClick={() => {
              setReadIds(notificationItems.map((item) => item.id))
              void message.info('已在当前页面标记为已读，尚未同步到后端')
            }}
          >
            全部标为已读
          </Button>
        }
        aside={
          <div className="operations-hero__aside-card">
            <span>未读消息</span>
            <strong>{notificationItems.length - readIds.length}</strong>
            <small>其中 2 项需要今天处理</small>
          </div>
        }
      />

      <GlassPanel>
        <SectionHeading
          eyebrow="INBOX"
          title="消息收件箱"
          description="按时间倒序展示与你相关的系统通知。"
          action={
            <Segmented
              value={filter}
              options={['全部', '未读']}
              onChange={(value) => setFilter(String(value))}
            />
          }
        />
        <div className="operations-approval-list">
          {visibleItems.length ? (
            visibleItems.map((item) => {
              const Icon = item.icon
              const unread = !readIds.includes(item.id)
              return (
                <button
                  key={item.id}
                  type="button"
                  className={`operations-approval operations-tone--${item.tone}`}
                  onClick={() =>
                    setReadIds((current) =>
                      current.includes(item.id) ? current : [...current, item.id],
                    )
                  }
                >
                  <span className="operations-approval__icon">
                    <Icon size={20} />
                  </span>
                  <div className="operations-approval__content">
                    <strong>{item.title}</strong>
                    <span className="operations-approval__summary">{item.detail}</span>
                    <span>{item.time}</span>
                  </div>
                  <StatusPill
                    label={unread ? item.type : '已读'}
                    tone={unread ? item.tone : 'slate'}
                  />
                </button>
              )
            })
          ) : (
            <div className="operations-empty-note">所有通知都已处理</div>
          )}
        </div>
      </GlassPanel>
    </div>
  )
}
