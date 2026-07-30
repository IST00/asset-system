import { Button, Progress, message } from 'antd'
import {
  AlertTriangle,
  ArrowUpRight,
  Camera,
  CheckCircle2,
  FileBarChart,
  Plus,
  QrCode,
  ScanLine,
} from 'lucide-react'
import { inventoryTasks } from './data'
import {
  GlassPanel,
  OperationsHero,
  OperationsMetrics,
  SectionHeading,
  StatusPill,
} from './OperationsUI'

export default function Inventory() {
  const activeTask = inventoryTasks[0]
  const progress = Math.round((activeTask.checked / activeTask.total) * 1000) / 10
  const announce = (content: string) =>
    void message.info(`${content}尚未接入后端接口，当前仅展示界面效果`)

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow="SMART INVENTORY"
        title="用一次扫码，确认资产此刻的位置"
        description="面向员工和盘点管理员优化的移动盘点工作台。盘点后端接口尚未建设，当前数据为玻璃风格演示视图。"
        icon={ScanLine}
        tone="cyan"
        actions={
          <>
            <Button
              type="primary"
              size="large"
              icon={<QrCode size={18} />}
              onClick={() => announce('扫码盘点')}
            >
              开始扫码盘点
            </Button>
            <Button size="large" icon={<Plus size={17} />} onClick={() => announce('创建盘点任务')}>
              创建盘点任务
            </Button>
          </>
        }
        aside={
          <div
            className="operations-progress-ring operations-tone--cyan"
            style={{ '--progress': `${progress}%` } as React.CSSProperties}
          >
            <div>
              <strong>{progress}%</strong>
              <span>总盘点进度</span>
            </div>
          </div>
        }
      />

      <OperationsMetrics
        items={[
          { label: '进行中任务', value: 2, hint: '最近截止 07月28日', tone: 'cyan' },
          { label: '待盘点资产', value: 344, hint: '其中个人资产 267 件', tone: 'blue' },
          { label: '异常待处理', value: 23, hint: '盘亏 9 · 信息不符 14', tone: 'red' },
          { label: '本季度完成率', value: '94.8%', hint: '较上季度 +2.6%', tone: 'green' },
        ]}
      />

      <div className="operations-split">
        <GlassPanel>
          <SectionHeading
            eyebrow="ACTIVE TASKS"
            title="盘点任务"
            description="按截止时间排序，优先处理即将到期与异常较多的任务。"
            action={
              <Button icon={<FileBarChart size={16} />} onClick={() => announce('盘点报告')}>
                盘点报告
              </Button>
            }
          />
          <div className="operations-task-list">
            {inventoryTasks.map((task) => {
              const taskProgress = Math.round((task.checked / task.total) * 100)
              return (
                <div key={task.id} className={`operations-task operations-tone--${task.tone}`}>
                  <div className="operations-task__progress">{taskProgress}%</div>
                  <div className="operations-task__content">
                    <strong>{task.name}</strong>
                    <span>
                      {task.scope} · 管理员：{task.owner}
                    </span>
                    <Progress percent={taskProgress} showInfo={false} size={['100%', 6]} />
                  </div>
                  <div className="operations-task__aside">
                    <StatusPill label={task.status} tone={task.tone} />
                    <small>截止 {task.deadline}</small>
                  </div>
                </div>
              )
            })}
          </div>
        </GlassPanel>

        <GlassPanel>
          <SectionHeading
            eyebrow="EXCEPTIONS"
            title="异常雷达"
            description="需要盘点管理员确认的最新异常。"
          />
          <div className="operations-card operations-tone--red">
            <span className="operations-card__icon">
              <AlertTriangle size={21} />
            </span>
            <h3>9 件资产疑似盘亏</h3>
            <p>员工已提交理由，其中 3 件需要责任管理员进一步核验。</p>
            <div className="operations-card__meta">
              <span>最近更新 8 分钟前</span>
              <ArrowUpRight size={15} />
            </div>
          </div>
          <div className="operations-card operations-tone--amber" style={{ marginTop: 12 }}>
            <span className="operations-card__icon">
              <Camera size={21} />
            </span>
            <h3>14 条信息不一致</h3>
            <p>地点、使用人或资产状态与系统记录不一致，已附现场照片。</p>
            <div className="operations-card__meta">
              <span>待批量确认</span>
              <ArrowUpRight size={15} />
            </div>
          </div>
          <div className="operations-card operations-tone--green" style={{ marginTop: 12 }}>
            <span className="operations-card__icon">
              <CheckCircle2 size={21} />
            </span>
            <h3>986 件已正常确认</h3>
            <p>正常结果将由系统自动确认，无需管理员逐条处理。</p>
          </div>
        </GlassPanel>
      </div>
    </div>
  )
}
