import { Button, Input, Select, Spin } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { Activity, Download, FileClock, Filter, Search, ShieldAlert } from 'lucide-react'
import { useMemo, useState } from 'react'
import { administrationApi } from '@/api/administration'
import StatePanel from '@/components/ui/StatePanel'
import type { Tone } from './data'
import {
  GlassPanel,
  OperationsHero,
  OperationsMetrics,
  SectionHeading,
  StatusPill,
} from './OperationsUI'

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

function formatTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'medium',
    hour12: false,
  }).format(date)
}

export default function AuditLogs() {
  const [keyword, setKeyword] = useState('')
  const [module, setModule] = useState('全部模块')
  const query = useQuery({ queryKey: ['audit-logs'], queryFn: administrationApi.auditLogs })
  const logs = useMemo(() => query.data ?? [], [query.data])
  const modules = useMemo(
    () => Array.from(new Set(logs.map((log) => log.resource_type))).sort(),
    [logs],
  )
  const filteredLogs = useMemo(() => {
    const normalized = keyword.trim().toLowerCase()
    return logs.filter((log) => {
      const matchesModule = module === '全部模块' || log.resource_type === module
      const searchable = [
        log.action,
        log.resource_type,
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
  const sensitiveCount = logs.filter((log) => actionRisk(log.action).label === '敏感').length
  const operatorCount = new Set(logs.map((log) => log.operator_id)).size
  const today = new Date().toDateString()
  const todayCount = logs.filter((log) => new Date(log.created_at).toDateString() === today).length

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow="AUDIT TRAIL"
        title="每一次资产变化，都能回到发生的那一刻"
        description="操作日志已连接后端，可按操作、资源类型、对象编号和操作人编号检索。"
        icon={FileClock}
        tone="slate"
        actions={
          <Button type="primary" size="large" icon={<Download size={17} />} disabled>
            导出接口暂未开放
          </Button>
        }
        aside={
          <div className="operations-hero__aside-card">
            <span>当前日志记录</span>
            <strong>{logs.length}</strong>
            <small>后端最近操作记录</small>
          </div>
        }
      />

      <OperationsMetrics
        items={[
          { label: '今日操作事件', value: todayCount, hint: '按浏览器本地日期统计', tone: 'blue' },
          { label: '活跃操作人', value: operatorCount, hint: '当前日志范围内去重', tone: 'cyan' },
          { label: '敏感操作', value: sensitiveCount, hint: '按操作类型识别', tone: 'red' },
          { label: '日志总数', value: logs.length, hint: '后端当前返回数量', tone: 'slate' },
        ]}
      />

      <GlassPanel>
        <SectionHeading
          eyebrow="SEARCH"
          title="操作日志"
          description="后端当前未返回 IP 地址，因此界面不再展示虚构 IP。"
        />
        <div className="operations-toolbar">
          <Input
            value={keyword}
            allowClear
            prefix={<Search size={15} />}
            placeholder="搜索操作、资源、对象、操作人或日志编号"
            onChange={(event) => setKeyword(event.target.value)}
          />
          <div className="operations-toolbar__filters">
            <Select
              value={module}
              style={{ width: 170 }}
              suffixIcon={<Filter size={14} />}
              options={['全部模块', ...modules].map((value) => ({ value, label: value }))}
              onChange={setModule}
            />
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

        {query.isLoading ? (
          <div className="operations-loading">
            <Spin />
          </div>
        ) : query.isError ? (
          <StatePanel
            mode="error"
            message="操作日志加载失败，请确认账号拥有审计查看权限和全量数据范围"
            retryLabel="重新加载"
            onRetry={() => void query.refetch()}
          />
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
                      {log.action}
                      <StatusPill label={risk.label} tone={risk.tone} />
                    </strong>
                    <span>
                      操作人 #{log.operator_id} · {log.resource_type} · 对象 #
                      {log.resource_id ?? '—'}
                    </span>
                    <span>
                      日志 #{log.id}
                      {log.reason ? ` · ${log.reason}` : ''}
                    </span>
                  </div>
                  <div className="operations-log__aside">
                    <strong>{formatTime(log.created_at)}</strong>
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
