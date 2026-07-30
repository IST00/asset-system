import { Button, Input, Select, Switch, message } from 'antd'
import {
  BellRing,
  Bot,
  Building2,
  Clock3,
  DatabaseBackup,
  HardDrive,
  Save,
  Settings as SettingsIcon,
  ShieldCheck,
} from 'lucide-react'
import { useState } from 'react'
import {
  GlassPanel,
  OperationsHero,
  OperationsMetrics,
  SectionHeading,
  StatusPill,
} from './OperationsUI'

export default function Settings() {
  const [feishuEnabled, setFeishuEnabled] = useState(true)
  const [failureAlerts, setFailureAlerts] = useState(true)
  const [sessionHours, setSessionHours] = useState('8')

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow="SYSTEM SETTINGS"
        title="让系统规则稳定运行，也保持透明"
        description="系统设置后端接口尚未建设，当前开关和参数仅用于展示玻璃风格界面。"
        icon={SettingsIcon}
        tone="slate"
        actions={
          <Button
            type="primary"
            size="large"
            icon={<Save size={17} />}
            onClick={() => void message.info('系统设置接口尚未开放，本次调整未保存到后端')}
          >
            保存全部设置
          </Button>
        }
        aside={
          <div className="operations-hero__aside-card">
            <span>系统运行状态</span>
            <strong>正常</strong>
            <small>最近健康检查：1 分钟前</small>
          </div>
        }
      />

      <OperationsMetrics
        items={[
          { label: '运行环境', value: '开发', hint: '本地 SQLite', tone: 'blue' },
          { label: '飞书连接', value: '正常', hint: '今天 09:00 已同步', tone: 'green' },
          { label: '文件占用', value: '18.6GB', hint: '容量使用 23%', tone: 'cyan' },
          { label: '最近备份', value: '02:10', hint: '备份校验通过', tone: 'violet' },
        ]}
      />

      <div className="operations-grid operations-grid--two">
        <GlassPanel>
          <SectionHeading
            eyebrow="INTEGRATIONS"
            title="组织与飞书集成"
            description="第一版用于登录、组织同步、审批与盘点通知。"
          />
          <div className="operations-settings-list">
            <div className="operations-setting">
              <span className="operations-setting__icon">
                <Building2 size={18} />
              </span>
              <div className="operations-setting__content">
                <strong>飞书组织同步</strong>
                <span>每天 09:00 自动同步人员、部门与在职状态</span>
              </div>
              <Switch checked={feishuEnabled} onChange={setFeishuEnabled} />
            </div>
            <div className="operations-setting">
              <span className="operations-setting__icon">
                <Bot size={18} />
              </span>
              <div className="operations-setting__content">
                <strong>飞书应用连接</strong>
                <span>App ID：cli_a7••••••9fd · 回调验证正常</span>
              </div>
              <StatusPill label="已连接" tone="green" />
            </div>
          </div>
          <Button
            block
            style={{ marginTop: 14 }}
            onClick={() => void message.info('连接测试接口尚未开放，当前未执行真实测试')}
          >
            测试飞书连接
          </Button>
        </GlassPanel>

        <GlassPanel>
          <SectionHeading
            eyebrow="SECURITY"
            title="安全策略"
            description="控制登录会话与异常访问提醒。"
          />
          <div className="operations-settings-list">
            <div className="operations-setting">
              <span className="operations-setting__icon">
                <Clock3 size={18} />
              </span>
              <div className="operations-setting__content">
                <strong>登录会话有效期</strong>
                <span>超过时长后需要重新登录</span>
              </div>
              <Select
                value={sessionHours}
                style={{ width: 100 }}
                options={[
                  { value: '4', label: '4 小时' },
                  { value: '8', label: '8 小时' },
                  { value: '12', label: '12 小时' },
                ]}
                onChange={setSessionHours}
              />
            </div>
            <div className="operations-setting">
              <span className="operations-setting__icon">
                <ShieldCheck size={18} />
              </span>
              <div className="operations-setting__content">
                <strong>登录失败锁定</strong>
                <span>连续 5 次失败后锁定账号 30 分钟</span>
              </div>
              <StatusPill label="已启用" tone="green" />
            </div>
          </div>
        </GlassPanel>

        <GlassPanel>
          <SectionHeading
            eyebrow="STORAGE"
            title="文件与备份"
            description="管理附件存储、临时导出文件和数据库备份。"
          />
          <div className="operations-settings-list">
            <div className="operations-setting">
              <span className="operations-setting__icon">
                <HardDrive size={18} />
              </span>
              <div className="operations-setting__content">
                <strong>文件存储目录</strong>
                <span>/data/asset-system/storage</span>
              </div>
              <Button size="small">查看</Button>
            </div>
            <div className="operations-setting">
              <span className="operations-setting__icon">
                <DatabaseBackup size={18} />
              </span>
              <div className="operations-setting__content">
                <strong>自动备份</strong>
                <span>每天 02:00 执行，保留最近 30 份</span>
              </div>
              <StatusPill label="正常" tone="green" />
            </div>
          </div>
        </GlassPanel>

        <GlassPanel>
          <SectionHeading
            eyebrow="ALERTS"
            title="系统告警"
            description="服务故障和任务失败时通知系统管理员。"
          />
          <div className="operations-settings-list">
            <div className="operations-setting">
              <span className="operations-setting__icon">
                <BellRing size={18} />
              </span>
              <div className="operations-setting__content">
                <strong>故障飞书告警</strong>
                <span>健康检查连续失败 3 次后发送告警</span>
              </div>
              <Switch checked={failureAlerts} onChange={setFailureAlerts} />
            </div>
            <div className="operations-setting">
              <span className="operations-setting__icon">
                <SettingsIcon size={18} />
              </span>
              <div className="operations-setting__content">
                <strong>告警接收群</strong>
                <span>资产系统运维群</span>
              </div>
              <Input value="资产系统运维群" readOnly style={{ width: 150 }} />
            </div>
          </div>
        </GlassPanel>
      </div>
    </div>
  )
}
