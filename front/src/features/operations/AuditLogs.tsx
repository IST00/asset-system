import { App, Button, Input, Segmented, Select, Spin } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { Activity, Download, FileClock, Filter, KeyRound, Search, ShieldAlert } from 'lucide-react'
import { useMemo, useState } from 'react'
import { administrationApi } from '@/api/administration'
import StatePanel from '@/components/ui/StatePanel'
import { beijingDateKey, formatBeijingDateTime } from '@/utils/dateTime'
import { auditActionLabel, auditResourceTypeLabel, securityEventLabel } from '@/utils/displayLabels'
import type { Tone } from './data'
import {
  GlassPanel,
  OperationsHero,
  OperationsMetrics,
  SectionHeading,
  StatusPill,
} from './OperationsUI'

type LogView = '操作日志' | '安全事件'

function actionRisk(action: string): { label: '普通' | '关注' | '敏感'; tone: Tone } {
  const normalized = action.toUpperCase()
  if (
    ['DELETE', 'DISABLE', 'ROLE', 'PERMISSION', 'REJECT', 'TERMINATE'].some((item) =>
      normalized.includes(item),
    )
  )
    return { label: '敏感', tone: 'red' }
  if (['UPDATE', 'APPROVE', 'IMPORT', 'RETRY'].some((item) => normalized.includes(item)))
    return { label: '关注', tone: 'amber' }
  return { label: '普通', tone: 'slate' }
}

function securityRisk(eventType: string): { label: '正常' | '关注' | '阻断'; tone: Tone } {
  if (['ACCOUNT_LOCKED', 'LOGIN_BLOCKED', 'RATE_LIMITED'].includes(eventType)) {
    return { label: '阻断', tone: 'red' }
  }
  if (['LOGIN_FAILURE', 'PASSWORD_RESET', 'SESSION_REVOKED'].includes(eventType)) {
    return { label: '关注', tone: 'amber' }
  }
  return { label: '正常', tone: 'green' }
}

function csvCell(value: unknown): string {
  const text = value == null ? '' : typeof value === 'string' ? value : JSON.stringify(value)
  return `"${text.split('"').join('""')}"`
}

function downloadCsv(filename: string, header: string[], rows: unknown[][]): void {
  const content = [header, ...rows].map((row) => row.map(csvCell).join(',')).join('\r\n')
  const blob = new Blob([`\uFEFF${content}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export default function AuditLogs() {
  const { message } = App.useApp()
  const [view, setView] = useState<LogView>('操作日志')
  const [keyword, setKeyword] = useState('')
  const [module, setModule] = useState('全部模块')
  const auditQuery = useQuery({
    queryKey: ['audit-logs'],
    queryFn: administrationApi.auditLogs,
    enabled: view === '操作日志',
  })
  const securityQuery = useQuery({
    queryKey: ['security-events'],
    queryFn: () => administrationApi.securityEvents(0, 100),
    enabled: view === '安全事件',
  })
  const logs = useMemo(() => auditQuery.data ?? [], [auditQuery.data])
  const securityEvents = useMemo(() => securityQuery.data?.items ?? [], [securityQuery.data?.items])
  const modules = useMemo(
    () => Array.from(new Set(logs.map((log) => log.resource_type))).sort(),
    [logs],
  )
  const filteredLogs = useMemo(() => {
    const normalized = keyword.trim().toLowerCase()
    return logs.filter((log) => {
      const matchesModule = module === '全部模块' || log.resource_type === module
      const searchable = [
        auditActionLabel(log.action),
        auditResourceTypeLabel(log.resource_type),
        String(log.resource_id ?? ''),
        String(log.operator_id),
        String(log.id),
        log.reason ?? '',
      ]
      return (
        matchesModule &&
        (!normalized || searchable.some((value) => value.toLowerCase().includes(normalized)))
      )
    })
  }, [keyword, logs, module])
  const filteredSecurityEvents = useMemo(() => {
    const normalized = keyword.trim().toLowerCase()
    return securityEvents.filter((event) => {
      const searchable = [
        securityEventLabel(event.event_type),
        event.username ?? '',
        event.ip_address ?? '',
        event.detail ?? '',
        String(event.user_id ?? ''),
        String(event.id),
      ]
      return !normalized || searchable.some((value) => value.toLowerCase().includes(normalized))
    })
  }, [keyword, securityEvents])

  const isSecurity = view === '安全事件'
  const currentCount = isSecurity ? securityEvents.length : logs.length
  const today = beijingDateKey(new Date().toISOString())
  const todayCount = (isSecurity ? securityEvents : logs).filter(
    (item) => beijingDateKey(item.created_at) === today,
  ).length
  const sensitiveCount = isSecurity
    ? securityEvents.filter((event) => securityRisk(event.event_type).label !== '正常').length
    : logs.filter((log) => actionRisk(log.action).label === '敏感').length
  const actorCount = isSecurity
    ? new Set(securityEvents.map((event) => event.username || event.ip_address).filter(Boolean))
        .size
    : new Set(logs.map((log) => log.operator_id)).size
  const activeQuery = isSecurity ? securityQuery : auditQuery
  const resultCount = isSecurity ? filteredSecurityEvents.length : filteredLogs.length

  const exportCurrent = () => {
    const date = beijingDateKey(new Date().toISOString())
    if (isSecurity) {
      downloadCsv(
        `安全事件-${date}.csv`,
        ['事件编号', '发生时间', '事件类型', '用户编号', '用户名', '来源 IP', '说明'],
        filteredSecurityEvents.map((event) => [
          event.id,
          formatBeijingDateTime(event.created_at),
          securityEventLabel(event.event_type),
          event.user_id ?? '',
          event.username ?? '',
          event.ip_address ?? '',
          event.detail ?? '',
        ]),
      )
    } else {
      downloadCsv(
        `审计日志-${date}.csv`,
        [
          '日志编号',
          '操作时间',
          '操作人编号',
          '动作',
          '资源类型',
          '资源编号',
          '原因',
          '变更前',
          '变更后',
        ],
        filteredLogs.map((log) => [
          log.id,
          formatBeijingDateTime(log.created_at),
          log.operator_id,
          auditActionLabel(log.action),
          auditResourceTypeLabel(log.resource_type),
          log.resource_id ?? '',
          log.reason ?? '',
          log.before_data ?? '',
          log.after_data ?? '',
        ]),
      )
    }
    void message.success(`已导出 ${resultCount} 条当前筛选记录`)
  }

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow="AUDIT & SECURITY"
        title="业务变更与登录安全，沿着同一条时间线追溯"
        description="操作日志记录业务数据变化；安全事件记录登录失败、账号锁定、改密和会话撤销。"
        icon={FileClock}
        tone="slate"
        actions={
          <Button
            type="primary"
            size="large"
            icon={<Download size={17} />}
            disabled={!resultCount}
            onClick={exportCurrent}
          >
            导出当前结果
          </Button>
        }
        aside={
          <div className="operations-hero__aside-card">
            <span>{isSecurity ? '当前安全事件' : '当前操作记录'}</span>
            <strong>{currentCount}</strong>
            <small>{isSecurity ? '最近 100 条服务端事件' : '后端最近操作记录'}</small>
          </div>
        }
      />

      <OperationsMetrics
        items={[
          { label: '今日事件', value: todayCount, hint: '按北京时间统计', tone: 'blue' },
          {
            label: isSecurity ? '涉及账号 / IP' : '活跃操作人',
            value: actorCount,
            hint: '当前返回范围内去重',
            tone: 'cyan',
          },
          {
            label: isSecurity ? '需关注或已阻断' : '敏感操作',
            value: sensitiveCount,
            hint: '按事件类型自动识别',
            tone: 'red',
          },
          { label: '当前记录', value: currentCount, hint: '来自后端真实数据', tone: 'slate' },
        ]}
      />

      <GlassPanel>
        <SectionHeading
          eyebrow="TRACE"
          title={view}
          description={
            isSecurity
              ? '安全事件由后端直接记录，默认保留 1 年；页面不会展示密码、令牌等敏感内容。'
              : '业务审计记录操作、资源、对象、原因以及变更前后快照。'
          }
          action={
            <Segmented<LogView>
              value={view}
              options={['操作日志', '安全事件']}
              onChange={(value) => {
                setView(value)
                setKeyword('')
                setModule('全部模块')
              }}
            />
          }
        />
        <div className="operations-toolbar">
          <Input
            value={keyword}
            allowClear
            prefix={<Search size={15} />}
            placeholder={
              isSecurity
                ? '搜索事件类型、用户名、IP、说明或事件编号'
                : '搜索操作、资源、对象、操作人或日志编号'
            }
            onChange={(event) => setKeyword(event.target.value)}
          />
          <div className="operations-toolbar__filters">
            {!isSecurity ? (
              <Select
                value={module}
                style={{ width: 170 }}
                suffixIcon={<Filter size={14} />}
                options={['全部模块', ...modules].map((value) => ({
                  value,
                  label: value === '全部模块' ? value : auditResourceTypeLabel(value),
                }))}
                onChange={setModule}
              />
            ) : null}
            <Button
              onClick={() => {
                setKeyword('')
                setModule('全部模块')
              }}
            >
              重置
            </Button>
          </div>
        </div>

        {activeQuery.isLoading ? (
          <div className="operations-loading">
            <Spin />
          </div>
        ) : activeQuery.isError ? (
          <StatePanel
            mode="error"
            message={`${view}加载失败，请确认账号拥有审计查看权限和全量数据范围`}
            retryLabel="重新加载"
            onRetry={() => void activeQuery.refetch()}
          />
        ) : isSecurity ? (
          filteredSecurityEvents.length ? (
            <div className="operations-log-list">
              {filteredSecurityEvents.map((event) => {
                const risk = securityRisk(event.event_type)
                return (
                  <article
                    key={event.id}
                    className={`operations-log operations-tone--${risk.tone}`}
                  >
                    <span className="operations-log__icon">
                      {risk.label === '阻断' ? <ShieldAlert size={18} /> : <KeyRound size={18} />}
                    </span>
                    <div className="operations-log__content">
                      <strong>
                        {securityEventLabel(event.event_type)}
                        <StatusPill label={risk.label} tone={risk.tone} />
                      </strong>
                      <span>
                        {event.username || '未知账号'}
                        {event.user_id ? ` · 用户 #${event.user_id}` : ''}
                        {event.ip_address ? ` · ${event.ip_address}` : ''}
                      </span>
                      <span>
                        事件 #{event.id}
                        {event.detail ? ` · ${event.detail}` : ''}
                      </span>
                    </div>
                    <div className="operations-log__aside">
                      <strong>{formatBeijingDateTime(event.created_at)}</strong>
                      <small>服务端记录时间</small>
                    </div>
                  </article>
                )
              })}
            </div>
          ) : (
            <StatePanel mode="empty" message="没有匹配的安全事件" />
          )
        ) : filteredLogs.length ? (
          <div className="operations-log-list">
            {filteredLogs.map((log) => {
              const risk = actionRisk(log.action)
              return (
                <article key={log.id} className={`operations-log operations-tone--${risk.tone}`}>
                  <span className="operations-log__icon">
                    {risk.label === '敏感' ? <ShieldAlert size={18} /> : <Activity size={18} />}
                  </span>
                  <div className="operations-log__content">
                    <strong>
                      {auditActionLabel(log.action)}
                      <StatusPill label={risk.label} tone={risk.tone} />
                    </strong>
                    <span>
                      操作人 #{log.operator_id} · {auditResourceTypeLabel(log.resource_type)} · 对象
                      #{log.resource_id ?? '—'}
                    </span>
                    <span>
                      日志 #{log.id}
                      {log.reason ? ` · ${log.reason}` : ''}
                    </span>
                  </div>
                  <div className="operations-log__aside">
                    <strong>{formatBeijingDateTime(log.created_at)}</strong>
                    <small>系统记录时间</small>
                  </div>
                </article>
              )
            })}
          </div>
        ) : (
          <StatePanel mode="empty" message="没有匹配的操作日志" />
        )}
      </GlassPanel>
    </div>
  )
}
