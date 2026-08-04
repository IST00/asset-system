import { App, Button, Input, Modal, Segmented, Spin, Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  CheckCircle2,
  CloudUpload,
  Clock3,
  Download,
  FileCheck2,
  FileDown,
  FileSpreadsheet,
  FileUp,
  History,
  Printer,
  RefreshCw,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { listAssets } from '@/api/assets'
import { exportsApi, type ExportJob, type ExportJobStatus } from '@/api/exports'
import {
  importApi,
  type ImportAction,
  type ImportJob,
  type ImportPreviewRow,
  type ImportStatus,
  type ImportType,
} from '@/api/imports'
import StatePanel from '@/components/ui/StatePanel'
import { parseAssetCodes } from '@/features/assets/assetModel'
import { useAuthStore } from '@/store/auth'
import type { Tone } from './data'
import {
  GlassPanel,
  OperationsHero,
  OperationsMetrics,
  SectionHeading,
  StatusPill,
} from './OperationsUI'

const typeMeta: Record<
  ImportType,
  {
    label: string
    permission: string
    exportPermission?: string
    exportFilename?: string
    description: string
    example: string
    tone: Tone
  }
> = {
  ASSET: {
    label: '资产台账',
    permission: 'asset:import',
    description: '历史资产整批预览后直接建账，保留原编码；缺少单位、来源或地点时进入待补充清单。',
    example: '资产编码、公司编码、分类编码、金额、日期与责任管理员',
    tone: 'green',
  },
  ORGANIZATION: {
    label: '公司编码',
    permission: 'organization:import',
    exportPermission: 'organization:export',
    exportFilename: '公司编码完整层级.xlsx',
    description: '按编码新增或更新公司树，支持父级关系、启停状态、差异预览和整批确认。',
    example: '编码、名称、上级编码、状态',
    tone: 'blue',
  },
  CATEGORY: {
    label: '资产分类',
    permission: 'asset-category:import',
    exportPermission: 'asset-category:export',
    exportFilename: '资产分类完整层级.xlsx',
    description: '按编码新增或更新分类树，校验默认单位、使用期限与父级关系。',
    example: '编码、名称、上级编码、使用期限、默认单位、状态',
    tone: 'violet',
  },
}

const statusMeta: Record<ImportStatus, { label: string; tone: Tone }> = {
  PREVIEW_READY: { label: '可确认', tone: 'green' },
  VALIDATION_FAILED: { label: '需修正', tone: 'red' },
  CONFIRMED: { label: '已入库', tone: 'blue' },
}

const actionMeta: Record<ImportAction, { label: string; tone: Tone }> = {
  CREATE: { label: '新增', tone: 'green' },
  UPDATE: { label: '更新', tone: 'blue' },
  UNCHANGED: { label: '无变化', tone: 'slate' },
}

type WorkspaceMode = 'IMPORT' | 'EXPORT'

const exportStatusMeta: Record<ExportJobStatus, { label: string; tone: Tone }> = {
  PROCESSING: { label: '生成中', tone: 'amber' },
  SUCCESS: { label: '可下载', tone: 'green' },
  FAILED: { label: '失败', tone: 'red' },
  EXPIRED: { label: '已过期', tone: 'slate' },
}

function formatBytes(value: number): string {
  if (value <= 0) return '0 B'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

function saveBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function dateTime(value?: string | null): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function rowPrimary(row: ImportPreviewRow, type: ImportType): { title: string; detail: string } {
  if (type === 'ASSET') {
    return {
      title: row.values['资产名称'] || `第 ${row.line} 行`,
      detail: [
        row.values['资产编码'] || '系统生成编码',
        row.values['所属公司编码'],
        row.values['资产分类编码'],
      ]
        .filter(Boolean)
        .join(' · '),
    }
  }
  return {
    title: row.values['名称'] || `第 ${row.line} 行`,
    detail: [row.values['编码'], row.values['上级编码'] ? `上级 ${row.values['上级编码']}` : '顶级']
      .filter(Boolean)
      .join(' · '),
  }
}

export default function Imports() {
  const { message } = App.useApp()
  const inputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()
  const permissions = useAuthStore((state) => state.user?.permissions ?? [])
  const availableTypes = useMemo(
    () =>
      (Object.keys(typeMeta) as ImportType[]).filter((type) =>
        permissions.includes(typeMeta[type].permission),
      ),
    [permissions],
  )
  const canExportAssets = permissions.includes('asset:export')
  const canPrintLabels = permissions.includes('asset:label:print')
  const canExportOrganizations = permissions.includes('organization:export')
  const canExportCategories = permissions.includes('asset-category:export')
  const hasExportCapability =
    canExportAssets || canPrintLabels || canExportOrganizations || canExportCategories
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>(
    availableTypes.length ? 'IMPORT' : 'EXPORT',
  )
  const [activeType, setActiveType] = useState<ImportType>(availableTypes[0] ?? 'ASSET')
  const [currentJob, setCurrentJob] = useState<ImportJob | null>(null)
  const [labelCodesText, setLabelCodesText] = useState('')

  useEffect(() => {
    if (!availableTypes.includes(activeType) && availableTypes[0]) {
      setActiveType(availableTypes[0])
    }
  }, [activeType, availableTypes])

  useEffect(() => {
    if (workspaceMode === 'IMPORT' && !availableTypes.length && hasExportCapability) {
      setWorkspaceMode('EXPORT')
    }
    if (workspaceMode === 'EXPORT' && !hasExportCapability && availableTypes.length) {
      setWorkspaceMode('IMPORT')
    }
  }, [availableTypes.length, hasExportCapability, workspaceMode])

  const historyQuery = useQuery({
    queryKey: ['import-jobs', activeType],
    queryFn: () => importApi.list(0, 20, activeType),
    enabled: availableTypes.includes(activeType),
  })
  const exportJobsQuery = useQuery({
    queryKey: ['export-jobs'],
    queryFn: exportsApi.page,
    enabled: hasExportCapability,
  })
  const previewMutation = useMutation({
    mutationFn: (file: File) => importApi.preview(activeType, file),
    onSuccess: async (job) => {
      setCurrentJob(job)
      await queryClient.invalidateQueries({ queryKey: ['import-jobs', activeType] })
      if (job.error_count) {
        void message.warning(`预检完成，发现 ${job.error_count} 个错误，请修正后重新上传`)
      } else {
        void message.success('服务端预检通过，请核对差异后确认导入')
      }
    },
    onError: (error) => void message.error(error instanceof Error ? error.message : '导入预检失败'),
  })
  const detailMutation = useMutation({
    mutationFn: importApi.detail,
    onSuccess: setCurrentJob,
  })
  const confirmMutation = useMutation({
    mutationFn: importApi.confirm,
    onSuccess: async (job) => {
      setCurrentJob(job)
      await queryClient.invalidateQueries({ queryKey: ['import-jobs', activeType] })
      await queryClient.invalidateQueries({ queryKey: ['assets'] })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      await queryClient.invalidateQueries({ queryKey: ['master-data'] })
      void message.success(`导入任务 ${job.job_no} 已整批确认`)
    },
    onError: (error) => void message.error(error instanceof Error ? error.message : '确认导入失败'),
  })
  const templateMutation = useMutation({
    mutationFn: () => importApi.template(activeType),
    onSuccess: (blob) => saveBlob(`${typeMeta[activeType].label}导入模板.xlsx`, blob),
  })
  const masterDataExportMutation = useMutation({
    mutationFn: (type: Extract<ImportType, 'ORGANIZATION' | 'CATEGORY'>) =>
      importApi.masterDataExport(type),
    onSuccess: (blob, type) => {
      const meta = typeMeta[type]
      saveBlob(meta.exportFilename ?? `${meta.label}完整层级.xlsx`, blob)
      void message.success(`${meta.label}完整层级已导出，可直接修改后重新上传`)
    },
    onError: (error) =>
      void message.error(error instanceof Error ? error.message : '完整层级导出失败'),
  })
  const reportMutation = useMutation({
    mutationFn: (job: ImportJob) => importApi.errorReport(job.id),
    onSuccess: (blob, job) => saveBlob(`${job.job_no}-校验报告.xlsx`, blob),
  })
  const assetExportMutation = useMutation({
    mutationFn: () => exportsApi.create({ job_type: 'ASSET_CSV' }),
    onSuccess: async (job) => {
      await queryClient.invalidateQueries({ queryKey: ['export-jobs'] })
      void message.success(`资产台账已生成，共 ${job.item_count} 件，可在下方任务记录下载`)
    },
  })
  const labelExportMutation = useMutation({
    mutationFn: async (rawCodes: string) => {
      const codes = parseAssetCodes(rawCodes)
      if (!codes.length) throw new Error('请先填写需要生成标签的资产编码')
      if (codes.length > 100) throw new Error('单次最多生成 100 张资产标签')
      const result = await listAssets({ page: 1, size: 100, asset_codes: codes })
      const assetsByCode = new Map(result.records.map((asset) => [asset.asset_code, asset]))
      const missingCodes = codes.filter((code) => !assetsByCode.has(code))
      if (missingCodes.length) {
        const preview = missingCodes.slice(0, 5).join('、')
        const suffix = missingCodes.length > 5 ? ` 等 ${missingCodes.length} 个编码` : ''
        throw new Error(`以下资产不存在或当前账号无权访问：${preview}${suffix}`)
      }
      return exportsApi.create({
        job_type: 'LABEL_PDF',
        asset_ids: codes
          .map((code) => assetsByCode.get(code)?.id)
          .filter((id): id is number => !!id),
      })
    },
    onSuccess: async (job) => {
      setLabelCodesText('')
      await queryClient.invalidateQueries({ queryKey: ['export-jobs'] })
      void message.success(`已生成 ${job.item_count} 张条码标签，可在下方任务记录下载`)
    },
    onError: (error) =>
      void message.error(error instanceof Error ? error.message : '资产标签生成失败'),
  })
  const downloadExportMutation = useMutation({
    mutationFn: exportsApi.download,
    onError: (error) =>
      void message.error(error instanceof Error ? error.message : '导出文件下载失败'),
  })

  const rows = currentJob?.rows ?? []
  const columns = useMemo<ColumnsType<ImportPreviewRow>>(
    () => [
      {
        title: '行号',
        dataIndex: 'line',
        width: 72,
      },
      {
        title: '导入内容',
        render: (_, row) => {
          const primary = rowPrimary(row, currentJob?.import_type ?? activeType)
          return (
            <div className="operations-table__primary">
              <strong>{primary.title}</strong>
              <small>{primary.detail}</small>
            </div>
          )
        },
      },
      {
        title: '处理动作',
        width: 100,
        render: (_, row) => {
          const meta = actionMeta[row.action]
          return <StatusPill label={meta.label} tone={meta.tone} />
        },
      },
      {
        title: '校验结果',
        render: (_, row) => (
          <div className="operations-import-validation">
            {row.errors.length ? (
              <span className="is-error">
                <AlertTriangle size={15} />
                {row.errors.join('；')}
              </span>
            ) : (
              <span className="is-success">
                <CheckCircle2 size={15} /> 字段校验通过
              </span>
            )}
            {row.warnings.length ? <small>{row.warnings.join('；')}</small> : null}
          </div>
        ),
      },
    ],
    [activeType, currentJob?.import_type],
  )

  const selectFile = () => inputRef.current?.click()
  const confirmJob = () => {
    if (!currentJob) return
    Modal.confirm({
      title: `确认整批导入 ${currentJob.row_count} 行？`,
      content:
        currentJob.import_type === 'ASSET'
          ? '确认后会直接建立正式历史资产，不再进入入库审批；全部记录在同一事务中写入。'
          : '确认后会按预览结果新增或更新基础资料，编码保持不变，并记录完整前后快照。',
      okText: '确认整批导入',
      cancelText: '继续核对',
      centered: true,
      onOk: () => confirmMutation.mutateAsync(currentJob),
    })
  }

  if (!availableTypes.length && !hasExportCapability) {
    return (
      <div className="operations-page">
        <StatePanel mode="empty" message="当前账号没有数据导入或导出权限" />
      </div>
    )
  }

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow={workspaceMode === 'IMPORT' ? 'SERVER IMPORT CENTER' : 'SECURE EXPORT CENTER'}
        title={
          workspaceMode === 'IMPORT'
            ? '真实导入任务：上传、预览差异、整批确认、全程留痕'
            : '真实导出中心：按权限生成台账、主数据与资产标签'
        }
        description={
          workspaceMode === 'IMPORT'
            ? 'CSV 与 XLSX 都交给后端统一校验。资产、公司编码和分类编码使用独立模板；任何错误都会阻止整批写入，不会出现部分成功。'
            : '资产台账由服务端按当前账号的数据范围和金额权限生成；公司、分类导出完整层级，资产标签生成 80 × 30 mm PDF。'
        }
        icon={workspaceMode === 'IMPORT' ? FileUp : FileDown}
        tone={workspaceMode === 'IMPORT' ? typeMeta[activeType].tone : 'blue'}
        actions={
          <>
            <Segmented
              className="operations-data-mode"
              value={workspaceMode}
              options={[
                ...(availableTypes.length ? [{ label: '导入', value: 'IMPORT' }] : []),
                ...(hasExportCapability ? [{ label: '导出', value: 'EXPORT' }] : []),
              ]}
              onChange={(value) => setWorkspaceMode(value as WorkspaceMode)}
            />
            {workspaceMode === 'IMPORT' ? (
              <>
                <Button
                  type="primary"
                  size="large"
                  icon={<CloudUpload size={18} />}
                  loading={previewMutation.isPending}
                  onClick={selectFile}
                >
                  上传 {typeMeta[activeType].label}
                </Button>
                <Button
                  size="large"
                  icon={<Download size={17} />}
                  loading={templateMutation.isPending}
                  onClick={() => templateMutation.mutate()}
                >
                  下载 XLSX 模板
                </Button>
              </>
            ) : canExportAssets ? (
              <Button
                type="primary"
                size="large"
                icon={<FileSpreadsheet size={17} />}
                loading={assetExportMutation.isPending}
                onClick={() => assetExportMutation.mutate()}
              >
                生成完整资产台账
              </Button>
            ) : null}
          </>
        }
        aside={
          <div className="operations-hero__aside-card">
            <span>{workspaceMode === 'IMPORT' ? '当前导入类型' : '导出文件策略'}</span>
            <strong>
              {workspaceMode === 'IMPORT' ? typeMeta[activeType].label : '24 小时有效'}
            </strong>
            <small>
              {workspaceMode === 'IMPORT'
                ? typeMeta[activeType].example
                : '服务端生成 · 权限过滤 · 下载留痕'}
            </small>
          </div>
        }
      />

      {workspaceMode === 'IMPORT' ? (
        <>
          <input
            ref={inputRef}
            type="file"
            accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            hidden
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) previewMutation.mutate(file)
              event.target.value = ''
            }}
          />

          <GlassPanel className="operations-import-switcher">
            <SectionHeading
              eyebrow="IMPORT DOMAIN"
              title="选择导入模块"
              description={typeMeta[activeType].description}
              action={
                <Segmented
                  value={activeType}
                  options={availableTypes.map((type) => ({
                    label: typeMeta[type].label,
                    value: type,
                  }))}
                  onChange={(value) => {
                    setActiveType(value as ImportType)
                    setCurrentJob(null)
                  }}
                />
              }
            />
          </GlassPanel>

          <OperationsMetrics
            items={[
              {
                label: '文件记录',
                value: currentJob?.row_count ?? 0,
                hint: currentJob?.original_name ?? '等待上传文件',
                tone: 'blue',
              },
              {
                label: '新增',
                value: currentJob?.create_count ?? 0,
                hint: '确认后创建',
                tone: 'green',
              },
              {
                label: '更新 / 无变化',
                value: `${currentJob?.update_count ?? 0} / ${currentJob?.unchanged_count ?? 0}`,
                hint: activeType === 'ASSET' ? '资产导入只新增' : '按编码计算差异',
                tone: 'violet',
              },
              {
                label: '错误 / 警告',
                value: `${currentJob?.error_count ?? 0} / ${currentJob?.warning_count ?? 0}`,
                hint: currentJob?.error_count ? '错误必须全部修正' : '警告允许确认',
                tone: currentJob?.error_count ? 'red' : 'amber',
              },
            ]}
          />

          <div className="operations-split">
            <button type="button" className="operations-upload" onClick={selectFile}>
              <span className="operations-upload__icon">
                <FileSpreadsheet size={28} strokeWidth={1.7} />
              </span>
              <h2>
                {previewMutation.isPending ? '正在由服务器校验文件…' : '拖入前先下载对应标准模板'}
              </h2>
              <p>{typeMeta[activeType].description}</p>
              <div className="operations-upload__formats">
                <span>.XLSX</span>
                <span>.CSV</span>
                <span>最多 2,000 行</span>
                <span>整批事务</span>
              </div>
            </button>

            <GlassPanel>
              <SectionHeading
                eyebrow="VALIDATION CONTRACT"
                title="不会把前端预检当成最终结果"
                description="文件内容、唯一字段、基础资料、层级循环和数据变化都由后端再次校验。"
              />
              <div className="operations-card operations-tone--green">
                <span className="operations-card__icon">
                  <FileCheck2 size={21} />
                </span>
                <h3>真正的服务端任务</h3>
                <p>预览任务、每行错误和警告、确认人、确认时间、前后差异与导入结果都会持久化。</p>
              </div>
              <div className="operations-card operations-tone--amber" style={{ marginTop: 12 }}>
                <span className="operations-card__icon">
                  <History size={21} />
                </span>
                <h3>历史迁移规则</h3>
                <p>资产导入允许单位、来源或地点为空或未匹配，保留原始文字并进入“待补充”清单。</p>
              </div>
            </GlassPanel>
          </div>

          {currentJob ? (
            <GlassPanel>
              <SectionHeading
                eyebrow={`PREVIEW · ${currentJob.job_no}`}
                title={`${typeMeta[currentJob.import_type].label}导入预览`}
                description={`上传于 ${dateTime(currentJob.created_at)}，共 ${currentJob.row_count} 行。确认前请核对新增、更新、警告与错误。`}
                action={
                  <div className="operations-import-actions">
                    <StatusPill
                      label={statusMeta[currentJob.status].label}
                      tone={statusMeta[currentJob.status].tone}
                    />
                    <Button
                      icon={<Download size={16} />}
                      loading={reportMutation.isPending}
                      onClick={() => reportMutation.mutate(currentJob)}
                    >
                      校验报告
                    </Button>
                    {currentJob.status === 'PREVIEW_READY' ? (
                      <Button
                        type="primary"
                        loading={confirmMutation.isPending}
                        onClick={confirmJob}
                      >
                        二次确认并导入
                      </Button>
                    ) : null}
                  </div>
                }
              />
              <div className="operations-import-preview">
                <Table<ImportPreviewRow>
                  rowKey="line"
                  columns={columns}
                  dataSource={rows}
                  pagination={{ pageSize: 20, showSizeChanger: false }}
                  scroll={{ x: 820 }}
                />
              </div>
            </GlassPanel>
          ) : null}

          <GlassPanel>
            <SectionHeading
              eyebrow="IMPORT HISTORY"
              title={`${typeMeta[activeType].label}导入记录`}
              description="这里只显示当前账号创建的真实服务端任务。"
              action={
                <Button
                  icon={<RefreshCw size={16} />}
                  loading={historyQuery.isFetching}
                  onClick={() => void historyQuery.refetch()}
                >
                  刷新
                </Button>
              }
            />
            {historyQuery.isLoading ? (
              <div className="operations-loading">
                <Spin />
              </div>
            ) : historyQuery.isError ? (
              <StatePanel
                mode="error"
                message="导入任务加载失败"
                retryLabel="重新加载"
                onRetry={() => void historyQuery.refetch()}
              />
            ) : historyQuery.data?.items.length ? (
              <div className="operations-table operations-import-history">
                <div className="operations-table__header">
                  <span>任务</span>
                  <span>记录</span>
                  <span>校验</span>
                  <span>状态</span>
                  <span>操作</span>
                </div>
                {historyQuery.data.items.map((job) => {
                  const status = statusMeta[job.status]
                  return (
                    <div key={job.id} className="operations-table__row">
                      <div className="operations-table__primary">
                        <strong>{job.job_no}</strong>
                        <small>
                          {job.original_name} · {dateTime(job.created_at)}
                        </small>
                      </div>
                      <span>{job.row_count} 行</span>
                      <span>
                        {job.error_count} 错误 / {job.warning_count} 警告
                      </span>
                      <StatusPill label={status.label} tone={status.tone} />
                      <Button
                        size="small"
                        loading={detailMutation.isPending && detailMutation.variables === job.id}
                        onClick={() => detailMutation.mutate(job.id)}
                      >
                        查看预览
                      </Button>
                    </div>
                  )
                })}
              </div>
            ) : (
              <div className="operations-empty-note">当前导入类型还没有任务记录</div>
            )}
          </GlassPanel>
        </>
      ) : (
        <>
          <OperationsMetrics
            items={[
              {
                label: '导出任务',
                value: exportJobsQuery.data?.total ?? 0,
                hint: '当前账号创建的服务端任务',
                tone: 'blue',
              },
              {
                label: '可下载',
                value:
                  exportJobsQuery.data?.items.filter((job) => job.status === 'SUCCESS').length ?? 0,
                hint: '文件生成后保留 24 小时',
                tone: 'green',
              },
              {
                label: '已导出资产',
                value:
                  exportJobsQuery.data?.items.reduce((total, job) => total + job.item_count, 0) ??
                  0,
                hint: '台账与标签任务合计',
                tone: 'violet',
              },
              {
                label: '权限模式',
                value: canExportAssets ? '数据范围' : '主数据',
                hint: canExportAssets ? '金额字段继续按权限控制' : '仅显示已授权导出项',
                tone: 'amber',
              },
            ]}
          />

          <div className="operations-export-grid">
            {canExportAssets ? (
              <GlassPanel className="operations-export-card operations-export-card--ledger">
                <span className="operations-export-card__icon">
                  <FileSpreadsheet size={24} />
                </span>
                <div className="operations-export-card__copy">
                  <span>ASSET LEDGER</span>
                  <h2>完整资产台账</h2>
                  <p>
                    导出当前账号有权查看的全部资产。金额字段、组织范围和数据范围都由后端重新校验。
                  </p>
                </div>
                <div className="operations-export-card__facts">
                  <span>CSV · UTF-8 BOM</span>
                  <span>服务端生成</span>
                  <span>操作留痕</span>
                </div>
                <Button
                  type="primary"
                  size="large"
                  icon={<FileDown size={17} />}
                  loading={assetExportMutation.isPending}
                  onClick={() => assetExportMutation.mutate()}
                >
                  生成资产台账
                </Button>
              </GlassPanel>
            ) : null}

            {canPrintLabels ? (
              <GlassPanel className="operations-export-card operations-export-card--label">
                <span className="operations-export-card__icon">
                  <Printer size={24} />
                </span>
                <div className="operations-export-card__copy">
                  <span>80 × 30 MM LABELS</span>
                  <h2>资产条码标签</h2>
                  <p>
                    粘贴资产编码，支持空格、逗号或换行分隔。系统会精确核对权限，单次最多 100 件。
                  </p>
                </div>
                <Input.TextArea
                  value={labelCodesText}
                  autoSize={{ minRows: 3, maxRows: 6 }}
                  placeholder={'例如：\nDS-IT-0001\nDS-IT-0002'}
                  onChange={(event) => setLabelCodesText(event.target.value)}
                />
                <Button
                  type="primary"
                  size="large"
                  icon={<Printer size={17} />}
                  loading={labelExportMutation.isPending}
                  onClick={() => labelExportMutation.mutate(labelCodesText)}
                >
                  生成标签 PDF
                </Button>
              </GlassPanel>
            ) : null}

            {canExportOrganizations || canExportCategories ? (
              <GlassPanel className="operations-export-card operations-export-card--master">
                <span className="operations-export-card__icon">
                  <FileCheck2 size={24} />
                </span>
                <div className="operations-export-card__copy">
                  <span>MASTER DATA SNAPSHOT</span>
                  <h2>主数据完整层级</h2>
                  <p>导出公司或资产分类的完整树结构，可直接在标准文件中维护后重新导入。</p>
                </div>
                <div className="operations-export-master-actions">
                  {canExportOrganizations ? (
                    <Button
                      size="large"
                      icon={<Download size={17} />}
                      loading={
                        masterDataExportMutation.isPending &&
                        masterDataExportMutation.variables === 'ORGANIZATION'
                      }
                      onClick={() => masterDataExportMutation.mutate('ORGANIZATION')}
                    >
                      导出公司层级
                    </Button>
                  ) : null}
                  {canExportCategories ? (
                    <Button
                      size="large"
                      icon={<Download size={17} />}
                      loading={
                        masterDataExportMutation.isPending &&
                        masterDataExportMutation.variables === 'CATEGORY'
                      }
                      onClick={() => masterDataExportMutation.mutate('CATEGORY')}
                    >
                      导出分类层级
                    </Button>
                  ) : null}
                </div>
                <small className="operations-export-card__note">
                  主数据文件直接下载，不占用临时导出任务额度。
                </small>
              </GlassPanel>
            ) : null}
          </div>

          {(canExportAssets || canPrintLabels) && (
            <GlassPanel>
              <SectionHeading
                eyebrow="EXPORT HISTORY"
                title="导出任务与下载记录"
                description="这里只显示当前账号创建的真实任务；过期文件需要重新生成。"
                action={
                  <Button
                    icon={<RefreshCw size={16} />}
                    loading={exportJobsQuery.isFetching}
                    onClick={() => void exportJobsQuery.refetch()}
                  >
                    刷新
                  </Button>
                }
              />
              {exportJobsQuery.isLoading ? (
                <div className="operations-loading">
                  <Spin />
                </div>
              ) : exportJobsQuery.isError ? (
                <StatePanel
                  mode="error"
                  message="导出任务加载失败"
                  retryLabel="重新加载"
                  onRetry={() => void exportJobsQuery.refetch()}
                />
              ) : exportJobsQuery.data?.items.length ? (
                <div className="operations-table operations-export-history">
                  <div className="operations-table__header">
                    <span>文件</span>
                    <span>类型</span>
                    <span>资产数</span>
                    <span>状态 / 有效期</span>
                    <span>操作</span>
                  </div>
                  {exportJobsQuery.data.items.map((job: ExportJob) => {
                    const status = exportStatusMeta[job.status]
                    return (
                      <div key={job.id} className="operations-table__row">
                        <div className="operations-table__primary">
                          <strong>{job.original_name}</strong>
                          <small>
                            {formatBytes(job.size_bytes)} · 创建于 {dateTime(job.created_at)}
                          </small>
                          {job.error_message ? <em>{job.error_message}</em> : null}
                        </div>
                        <span>{job.job_type === 'ASSET_CSV' ? '资产台账' : '条码标签'}</span>
                        <span>{job.item_count} 件</span>
                        <div className="operations-export-status">
                          <StatusPill label={status.label} tone={status.tone} />
                          <small>
                            <Clock3 size={13} />
                            {dateTime(job.expires_at)}
                          </small>
                        </div>
                        <Button
                          type="primary"
                          size="small"
                          icon={<Download size={15} />}
                          disabled={job.status !== 'SUCCESS'}
                          loading={
                            downloadExportMutation.isPending &&
                            downloadExportMutation.variables?.id === job.id
                          }
                          onClick={() => downloadExportMutation.mutate(job)}
                        >
                          下载
                        </Button>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="operations-empty-note">
                  还没有导出任务，可以从上方生成资产台账或标签
                </div>
              )}
            </GlassPanel>
          )}
        </>
      )}
    </div>
  )
}
