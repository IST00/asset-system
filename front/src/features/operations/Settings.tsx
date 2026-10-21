import { App, Button, Spin } from 'antd'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  Bot,
  Clock3,
  Database,
  DatabaseBackup,
  HardDrive,
  RefreshCw,
  Settings as SettingsIcon,
  ShieldCheck,
} from 'lucide-react'
import { feishuApi } from '@/api/feishu'
import { systemApi } from '@/api/system'
import StatePanel from '@/components/ui/StatePanel'
import { formatBeijingDateTime } from '@/utils/dateTime'
import {
  GlassPanel,
  OperationsHero,
  OperationsMetrics,
  SectionHeading,
  StatusPill,
} from './OperationsUI'

const profileLabel: Record<string, string> = {
  dev: '开发环境',
  development: '开发环境',
  test: '测试环境',
  testing: '测试环境',
  prod: '生产环境',
  production: '生产环境',
}

const feishuLabel = {
  FORMAL_CONFIGURED: '正式配置已提供',
  LOCAL_SIMULATION: '仅本地模拟',
  NOT_CONFIGURED: '未配置',
} as const

export default function Settings() {
  const { message } = App.useApp()
  const query = useQuery({
    queryKey: ['system-status'],
    queryFn: systemApi.status,
    refetchInterval: 60_000,
  })
  const status = query.data
  const syncFeishu = useMutation({
    mutationFn: feishuApi.syncAll,
    onSuccess: (result) => {
      message.success(
        `飞书同步完成：${result.departments ?? 0} 个部门、${result.users ?? 0} 个用户`,
      )
      void query.refetch()
    },
    onError: (error) => {
      const isTimeout = error.message.includes('timeout')
      message.error(
        isTimeout
          ? '飞书组织较大，同步仍在处理中，请稍后刷新查看结果'
          : '飞书同步失败，请检查正式配置与权限',
      )
    },
  })
  const configuredCount = status
    ? [
        status.feishu.formal_configured,
        status.file_storage.configured,
        status.backup.configured,
      ].filter(Boolean).length
    : 0

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow="SYSTEM STATUS"
        title="系统能力是否真的可用，在这里如实呈现"
        description="本页读取后端实时状态，只展示已配置能力；不会把本地模拟、占位配置或未接入功能显示为正常。"
        icon={SettingsIcon}
        tone="slate"
        actions={
          <Button
            type="primary"
            size="large"
            icon={<RefreshCw size={17} />}
            loading={query.isFetching}
            onClick={() => void query.refetch()}
          >
            刷新状态
          </Button>
        }
        aside={
          <div className="operations-hero__aside-card">
            <span>应用健康状态</span>
            <strong>{status?.application.healthy ? '正常' : '待确认'}</strong>
            <small>
              {status
                ? `服务时间 ${formatBeijingDateTime(status.application.server_time)}`
                : '正在读取后端'}
            </small>
          </div>
        }
      />

      {query.isLoading ? (
        <div className="operations-loading">
          <Spin />
        </div>
      ) : query.isError || !status ? (
        <StatePanel
          mode="error"
          message="系统状态加载失败，请确认后端服务可访问"
          retryLabel="重新加载"
          onRetry={() => void query.refetch()}
        />
      ) : (
        <>
          <OperationsMetrics
            items={[
              {
                label: '运行环境',
                value: profileLabel[status.profile] ?? status.profile,
                hint: status.application.name,
                tone: 'blue',
              },
              {
                label: '数据库',
                value: status.database.connected ? '已连接' : '异常',
                hint: status.database.label,
                tone: status.database.connected ? 'green' : 'red',
              },
              {
                label: '外部能力',
                value: `${configuredCount}/3`,
                hint: '飞书、文件存储、备份',
                tone: configuredCount === 3 ? 'green' : 'amber',
              },
              {
                label: '会话时长',
                value: status.security.session_hours
                  ? `${status.security.session_hours} 小时`
                  : '未识别',
                hint: '来自后端 JWT 配置',
                tone: 'cyan',
              },
            ]}
          />

          <div className="operations-grid operations-grid--two">
            <GlassPanel>
              <SectionHeading
                eyebrow="RUNTIME"
                title="运行与数据库"
                description="当前应用实例实际使用的环境和数据库连接。"
              />
              <div className="operations-settings-list">
                <div className="operations-setting">
                  <span className="operations-setting__icon">
                    <Database size={18} />
                  </span>
                  <div className="operations-setting__content">
                    <strong>{status.database.label}</strong>
                    <span>驱动类型：{status.database.dialect}</span>
                  </div>
                  <StatusPill
                    label={status.database.connected ? '已连接' : '异常'}
                    tone={status.database.connected ? 'green' : 'red'}
                  />
                </div>
                <div className="operations-setting">
                  <span className="operations-setting__icon">
                    <Clock3 size={18} />
                  </span>
                  <div className="operations-setting__content">
                    <strong>登录会话有效期</strong>
                    <span>由后端统一配置，前端不能在此页面伪修改</span>
                  </div>
                  <StatusPill
                    label={
                      status.security.session_hours
                        ? `${status.security.session_hours} 小时`
                        : '未识别'
                    }
                    tone="blue"
                  />
                </div>
              </div>
            </GlassPanel>

            <GlassPanel>
              <SectionHeading
                eyebrow="INTEGRATION"
                title="飞书集成"
                description="区分正式配置与开发环境本地模拟能力。"
              />
              <div className="operations-settings-list">
                <div className="operations-setting">
                  <span className="operations-setting__icon">
                    <Bot size={18} />
                  </span>
                  <div className="operations-setting__content">
                    <strong>登录、组织同步与通知</strong>
                    <span>
                      {status.feishu.formal_configured
                        ? '后端检测到正式飞书配置；仍需在真实租户完成回调与权限验收。'
                        : status.feishu.local_simulation_available
                          ? '当前仅开放本地模拟接口，不代表正式飞书已连接。'
                          : '当前环境没有检测到飞书应用配置。'}
                    </span>
                  </div>
                  <StatusPill
                    label={feishuLabel[status.feishu.mode]}
                    tone={
                      status.feishu.formal_configured
                        ? 'green'
                        : status.feishu.local_simulation_available
                          ? 'amber'
                          : 'slate'
                    }
                  />
                </div>
                <div className="operations-setting">
                  <span className="operations-setting__icon">
                    <RefreshCw size={18} />
                  </span>
                  <div className="operations-setting__content">
                    <strong>飞书组织同步</strong>
                    <span>拉取部门与用户，并绑定飞书身份用于登录和消息推送。</span>
                  </div>
                  <Button
                    type="primary"
                    loading={syncFeishu.isPending}
                    onClick={() => syncFeishu.mutate()}
                  >
                    同步
                  </Button>
                </div>
              </div>
            </GlassPanel>

            <GlassPanel>
              <SectionHeading
                eyebrow="STORAGE"
                title="文件与附件存储"
                description="资产照片、维修附件、报废附件需要独立文件存储能力。"
              />
              <div className="operations-settings-list">
                <div className="operations-setting">
                  <span className="operations-setting__icon">
                    <HardDrive size={18} />
                  </span>
                  <div className="operations-setting__content">
                    <strong>业务文件存储</strong>
                    <span>
                      {status.file_storage.configured
                        ? '已检测到文件存储配置，仍需执行上传下载验收。'
                        : '未配置文件存储，因此附件模块尚不能作为正式能力使用。'}
                    </span>
                  </div>
                  <StatusPill
                    label={status.file_storage.configured ? '已配置' : '未配置'}
                    tone={status.file_storage.configured ? 'green' : 'amber'}
                  />
                </div>
              </div>
            </GlassPanel>

            <GlassPanel>
              <SectionHeading
                eyebrow="RESILIENCE"
                title="备份与安全加固"
                description="只展示检测到的配置，不虚构最近备份时间或安全状态。"
              />
              <div className="operations-settings-list">
                <div className="operations-setting">
                  <span className="operations-setting__icon">
                    <DatabaseBackup size={18} />
                  </span>
                  <div className="operations-setting__content">
                    <strong>数据库与附件备份</strong>
                    <span>
                      {status.backup.configured
                        ? '已检测到备份目标配置；恢复演练仍需在部署环境验收。'
                        : '未检测到备份目标或备份命令配置。'}
                    </span>
                  </div>
                  <StatusPill
                    label={status.backup.configured ? '已配置' : '未配置'}
                    tone={status.backup.configured ? 'green' : 'red'}
                  />
                </div>
                <div className="operations-setting">
                  <span className="operations-setting__icon">
                    <ShieldCheck size={18} />
                  </span>
                  <div className="operations-setting__content">
                    <strong>登录锁定与接口限流</strong>
                    <span>
                      连续 {status.security.login_lock_threshold} 次失败锁定{' '}
                      {status.security.login_lock_minutes} 分钟 · 登录 IP 每分钟{' '}
                      {status.security.login_rate_limit_per_minute} 次 · 用户接口每分钟{' '}
                      {status.security.user_rate_limit_per_minute} 次
                    </span>
                  </div>
                  <StatusPill
                    label={
                      status.security.login_failure_lock_configured &&
                      status.security.rate_limit_configured
                        ? '已加固'
                        : '待完善'
                    }
                    tone={
                      status.security.login_failure_lock_configured &&
                      status.security.rate_limit_configured
                        ? 'green'
                        : 'amber'
                    }
                  />
                </div>
              </div>
            </GlassPanel>
          </div>
        </>
      )}
    </div>
  )
}
