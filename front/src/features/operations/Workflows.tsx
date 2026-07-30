import { Button, Segmented, Spin, message } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeftRight, ArrowUpRight, PackageCheck, Plus, RotateCcw, Wrench } from 'lucide-react'
import { useMemo, useState } from 'react'
import { operationApi, type OperationRequest } from '@/api/operations'
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
}

const flowTypes = [
  {
    name: '资产入库',
    description: '登记采购信息并提交审批，审批完成后生成正式资产',
    icon: Plus,
    operationTypes: ['STOCK_IN'],
    tone: 'green' as const,
  },
  {
    name: '资产领用',
    description: '分配个人或公共资产并进入审批与确认流程',
    icon: PackageCheck,
    operationTypes: ['PERSONAL_USE', 'PUBLIC_USE'],
    tone: 'blue' as const,
  },
  {
    name: '资产退库',
    description: '解除使用责任并记录设备验收结果',
    icon: RotateCcw,
    operationTypes: ['PERSONAL_RETURN', 'PUBLIC_RETURN'],
    tone: 'cyan' as const,
  },
  {
    name: '资产调拨',
    description: '跨部门、公司或地点调整资产归属',
    icon: ArrowLeftRight,
    operationTypes: ['TRANSFER'],
    tone: 'violet' as const,
  },
  {
    name: '维修处理',
    description: '记录送修与维修完成结果，形成完整维修轨迹',
    icon: Wrench,
    operationTypes: ['REPAIR_START', 'REPAIR_COMPLETE'],
    tone: 'amber' as const,
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

export default function Workflows() {
  const [filter, setFilter] = useState('全部')
  const currentUserId = useAuthStore((state) => state.user?.id)
  const query = useQuery({
    queryKey: ['operation-requests'],
    queryFn: () => operationApi.list(0, 50),
  })
  const records = useMemo(() => query.data?.items ?? [], [query.data])
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

  const explainPendingForm = () => {
    void message.info('流程查询已接入后端；流程发起表单正在按后端字段继续完善。')
  }

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow="ASSET LIFECYCLE"
        title="让资产流转，每一步都有据可查"
        description="当前列表已连接正式后端，统一展示入库、领用、退库、调拨与维修的审批和执行状态。"
        icon={ArrowLeftRight}
        tone="blue"
        actions={
          <Button
            type="primary"
            size="large"
            icon={<Plus size={17} />}
            onClick={explainPendingForm}
          >
            发起业务流程
          </Button>
        }
        aside={
          <div className="operations-hero__aside-card">
            <span>当前流程总数</span>
            <strong>{query.data?.total ?? 0}</strong>
            <small>数据来自后端业务流程接口</small>
          </div>
        }
      />

      <OperationsMetrics
        items={[
          { label: '审批处理中', value: pendingApproval, hint: '等待审批任务完成', tone: 'blue' },
          { label: '执行处理中', value: processing, hint: '后端正在变更资产状态', tone: 'amber' },
          { label: '已完成', value: completed, hint: '本次查询范围内', tone: 'green' },
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
          description="卡片数量根据当前后端流程数据实时统计。"
        />
        <div className="operations-grid operations-grid--five">
          {flowTypes.map(({ name, description, icon: Icon, operationTypes, tone }) => {
            const count = records.filter((record) =>
              operationTypes.includes(record.operation_type),
            ).length
            return (
              <button
                key={name}
                type="button"
                className={`operations-card operations-tone--${tone}`}
                onClick={explainPendingForm}
              >
                <span className="operations-card__icon">
                  <Icon aria-hidden="true" size={21} strokeWidth={1.8} />
                </span>
                <h3>{name}</h3>
                <p>{description}</p>
                <div className="operations-card__meta">
                  <span>{count} 条流程记录</span>
                  <ArrowUpRight aria-hidden="true" size={15} />
                </div>
              </button>
            )
          })}
        </div>
      </GlassPanel>

      <GlassPanel>
        <SectionHeading
          eyebrow="RECENT ACTIVITY"
          title="最近流程"
          description="显示后端返回的最近 50 条流程记录。"
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
                  <StatusPill label={status.label} tone={status.tone} />
                </div>
              )
            })}
          </div>
        ) : (
          <StatePanel mode="empty" message="当前筛选下暂无流程记录" />
        )}
      </GlassPanel>
    </div>
  )
}
