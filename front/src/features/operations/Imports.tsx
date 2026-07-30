import { Button, message } from 'antd'
import {
  ArrowDownToLine,
  CloudUpload,
  Download,
  FileCheck2,
  FileSpreadsheet,
  FileUp,
  History,
} from 'lucide-react'
import { importJobs } from './data'
import {
  GlassPanel,
  OperationsHero,
  OperationsMetrics,
  SectionHeading,
  StatusPill,
} from './OperationsUI'

export default function Imports() {
  const announce = (content: string) =>
    void message.info(`${content}尚未接入后端接口，当前仅展示界面效果`)

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow="DATA EXCHANGE"
        title="让批量数据进入系统前，先经过一次体检"
        description="导入导出后端接口尚未建设，当前页面仅展示未来的模板校验、预览和结果管理体验。"
        icon={FileUp}
        tone="green"
        actions={
          <>
            <Button
              type="primary"
              size="large"
              icon={<CloudUpload size={18} />}
              onClick={() => announce('新建导入任务')}
            >
              新建导入任务
            </Button>
            <Button size="large" icon={<Download size={17} />} onClick={() => announce('模板下载')}>
              下载标准模板
            </Button>
          </>
        }
        aside={
          <div className="operations-hero__aside-card">
            <span>本月数据交换</span>
            <strong>28</strong>
            <small>累计处理 3,642 条记录</small>
          </div>
        }
      />

      <OperationsMetrics
        items={[
          { label: '今日导入', value: 4, hint: '共 324 条数据', tone: 'green' },
          { label: '待确认任务', value: 2, hint: '校验已完成', tone: 'amber' },
          { label: '今日导出', value: 7, hint: '文件保留 24 小时', tone: 'blue' },
          { label: '数据成功率', value: '98.7%', hint: '本月平均', tone: 'cyan' },
        ]}
      />

      <div className="operations-split">
        <button type="button" className="operations-upload" onClick={() => announce('文件选择器')}>
          <span className="operations-upload__icon">
            <FileSpreadsheet size={28} strokeWidth={1.7} />
          </span>
          <h2>拖入 Excel 文件开始导入</h2>
          <p>
            系统会先完成字段、编码和重复数据校验；确认预览结果后才会正式写入，不会直接覆盖现有数据。
          </p>
          <div className="operations-upload__formats">
            <span>.XLSX</span>
            <span>最大 20MB</span>
            <span>编码按文本读取</span>
          </div>
        </button>

        <GlassPanel>
          <SectionHeading
            eyebrow="TEMPLATES"
            title="常用模板"
            description="下载后保留表头与字段说明。"
          />
          <div className="operations-card operations-tone--blue">
            <span className="operations-card__icon">
              <ArrowDownToLine size={21} />
            </span>
            <h3>资产台账模板</h3>
            <p>适用于新增资产和历史资产迁移，共 28 个标准字段。</p>
            <div className="operations-card__meta">
              <span>更新于 2026-07-18</span>
              <Download size={15} />
            </div>
          </div>
          <div className="operations-card operations-tone--violet" style={{ marginTop: 12 }}>
            <span className="operations-card__icon">
              <FileCheck2 size={21} />
            </span>
            <h3>基础资料模板</h3>
            <p>公司、分类、地点和供应商均可按编码增量更新。</p>
            <div className="operations-card__meta">
              <span>6 类工作表</span>
              <Download size={15} />
            </div>
          </div>
        </GlassPanel>
      </div>

      <GlassPanel>
        <SectionHeading
          eyebrow="HISTORY"
          title="最近任务"
          description="导入错误文件和导出结果均在 24 小时后自动失效。"
          action={
            <Button icon={<History size={16} />} onClick={() => announce('全部记录')}>
              全部记录
            </Button>
          }
        />
        <div className="operations-table">
          <div className="operations-table__header">
            <span>任务类型</span>
            <span>文件</span>
            <span>操作人</span>
            <span>处理结果</span>
            <span>状态</span>
          </div>
          {importJobs.map((job) => (
            <div key={job.id} className="operations-table__row">
              <strong>{job.module}</strong>
              <div className="operations-table__primary">
                <strong>{job.fileName}</strong>
                <small>
                  {job.id} · {job.createdAt}
                </small>
              </div>
              <span>{job.operator}</span>
              <span>
                {job.success}/{job.total} 成功{job.failed ? ` · ${job.failed} 失败` : ''}
              </span>
              <StatusPill label={job.status} tone={job.tone} />
            </div>
          ))}
        </div>
      </GlassPanel>
    </div>
  )
}
