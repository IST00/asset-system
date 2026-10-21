import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Button,
  Checkbox,
  DatePicker,
  Drawer,
  Form,
  Input,
  Modal,
  Pagination,
  Popover,
  Select,
  Skeleton,
  QRCode,
  Table,
  message,
} from 'antd'
import type { ColumnType, ColumnsType, TableRowSelection } from 'antd/es/table/interface'
import dayjs from 'dayjs'
import type { Dayjs } from 'dayjs'
import {
  Clock3,
  Columns3,
  Download,
  FileSpreadsheet,
  Filter,
  History,
  ListFilter,
  PackageMinus,
  PencilLine,
  Plus,
  Printer,
  RotateCcw,
  Search,
  SlidersHorizontal,
  UserRoundCog,
} from 'lucide-react'
import type { Key } from 'react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { authApi } from '@/api'
import { assetManagementApi } from '@/api/assetManagement'
import { assetUsageReturnApi } from '@/api/assetUsageReturn'
import { assetQueryToExportFilters, exportsApi, type ExportJob } from '@/api/exports'
import http from '@/api/http'
import type { TreeItem } from '@/api/administration'
import { getAsset, listAssets, loadAssetReferences } from '@/api/assets'
import PageHeader from '@/components/ui/PageHeader'
import StatePanel from '@/components/ui/StatePanel'
import { getAssetStatusMeta } from '@/features/assets/assetModel'
import type { AssetListQuery, AssetStatus, AssetSummary } from '@/features/assets/types'
import { useAuthStore } from '@/store/auth'
import {
  buildAssetListQuery,
  canCreateAsset,
  getAssetStatusOptions,
  getAvailableColumns,
  getDefaultColumns,
  getNextQueryRevision,
} from './listModel'
import type { AssetColumnKey, AssetListFilterValues } from './listModel'
import { formatAssetAmount, formatAssetDate } from './listFormatters'
import useMobileViewport from './useMobileViewport'
import './AssetList.css'

const { RangePicker } = DatePicker

const statusOptions = getAssetStatusOptions()
const loadingColumns = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
const loadingRows = [0, 1, 2, 3, 4, 5]
const loadingCards = [0, 1, 2, 3]

const commonTextFilters: Array<{
  key: 'company_name' | 'category_name' | 'department_name' | 'location_name'
  labelKey: string
}> = [
  { key: 'company_name', labelKey: 'assets.list.filters.company' },
  { key: 'category_name', labelKey: 'assets.list.filters.category' },
  { key: 'department_name', labelKey: 'assets.list.filters.department' },
  { key: 'location_name', labelKey: 'assets.list.filters.location' },
]

const moreTextFilters: Array<{
  key: 'user_name' | 'manager_name' | 'supplier_name' | 'source_name'
  labelKey: string
}> = [
  { key: 'user_name', labelKey: 'assets.list.filters.user' },
  { key: 'manager_name', labelKey: 'assets.list.filters.manager' },
  { key: 'supplier_name', labelKey: 'assets.list.filters.supplier' },
  { key: 'source_name', labelKey: 'assets.list.filters.source' },
]

const emptyFilters: AssetListFilterValues = {}
const initialPageSize = 50 as const

interface BatchEditFormValues {
  category_id?: number
  unit_id?: number
  source_id?: number
  location_id?: number
  manager_id?: number
  supplier_id?: number
  holder_user_id?: number
  public_object_id?: number
  usage_department_id?: number
  remark?: string
  reason: string
}

const flattenTree = (items: TreeItem[]): TreeItem[] =>
  items.flatMap((item) => [item, ...flattenTree(item.children ?? [])])

function valueOrDash(value: string | undefined): string {
  return value || '—'
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

const exportStatusMeta: Record<
  ExportJob['status'],
  { label: string; tone: 'brand' | 'success' | 'danger' | 'muted' }
> = {
  PROCESSING: { label: '生成中', tone: 'brand' },
  SUCCESS: { label: '可下载', tone: 'success' },
  FAILED: { label: '生成失败', tone: 'danger' },
  EXPIRED: { label: '已过期', tone: 'muted' },
}

export default function AssetList() {
  const { i18n, t } = useTranslation()
  const isMobile = useMobileViewport()
  const permissions = useAuthStore((state) => state.user?.permissions)
  const currentUserId = useAuthStore((state) => state.user?.id)
  const canCreate = canCreateAsset(permissions)
  const canSelfReturn = permissions?.includes('asset:return:self') ?? false
  const canViewAllAssets = permissions?.includes('asset:usage:manage') ?? false
  const canTransferHandover = canViewAllAssets
  const canExport = permissions?.includes('asset:export') ?? false
  const canPrintLabels = permissions?.includes('asset:label:print') ?? false
  const locale = i18n.resolvedLanguage || i18n.language || 'zh-CN'
  const [draft, setDraft] = useState<AssetListFilterValues>(emptyFilters)
  const [query, setQuery] = useState<AssetListQuery>(() =>
    buildAssetListQuery(emptyFilters, initialPageSize),
  )
  const [assetCodesText, setAssetCodesText] = useState('')
  const [assetCodesOpen, setAssetCodesOpen] = useState(false)
  const [moreFiltersOpen, setMoreFiltersOpen] = useState(false)
  const availableColumns = useMemo(() => getAvailableColumns(permissions), [permissions])
  const [selectedColumns, setSelectedColumns] = useState<AssetColumnKey[]>(() =>
    getDefaultColumns('desktop'),
  )
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([])
  const [batchEditOpen, setBatchEditOpen] = useState(false)
  const [returnConfirmOpen, setReturnConfirmOpen] = useState(false)
  const [handoverOpen, setHandoverOpen] = useState(false)
  const [handoverResult, setHandoverResult] = useState<{
    handoverNo: string
    handoverToken: string
    assetCount: number
  } | null>(null)
  const [batchEditAsset, setBatchEditAsset] = useState<AssetSummary | null>(null)
  const [exportJobsOpen, setExportJobsOpen] = useState(false)
  const [batchForm] = Form.useForm<BatchEditFormValues>()
  const [handoverForm] = Form.useForm<{ reason?: string }>()
  const [queryRevision, setQueryRevision] = useState(0)
  const preferenceAppliedRef = useRef(false)
  const queryClient = useQueryClient()
  const location = useLocation()
  const navigate = useNavigate()

  const preferenceQuery = useQuery({
    queryKey: ['auth', 'preferences'],
    queryFn: authApi.preferences,
  })

  const preferenceMutation = useMutation({
    mutationFn: authApi.updatePreferences,
    onSuccess: (preferences) => {
      queryClient.setQueryData(['auth', 'preferences'], preferences)
    },
    onError: (error: Error) => void message.error(error.message || '列表偏好保存失败'),
  })

  useEffect(() => {
    const locationState = location.state as { transferHandoverCompleted?: boolean } | null
    if (!locationState?.transferHandoverCompleted) return
    void message.success('资产交接已完成，资产已归属当前账号')
    navigate(location.pathname, { replace: true, state: null })
  }, [location.pathname, location.state, navigate])

  useEffect(() => {
    if (!preferenceQuery.data || preferenceAppliedRef.current) return
    preferenceAppliedRef.current = true
    const preferredColumns = preferenceQuery.data.asset_list_columns.filter(
      (column): column is AssetColumnKey => availableColumns.includes(column as AssetColumnKey),
    )
    setSelectedColumns(
      preferredColumns.length > 0 ? preferredColumns : getDefaultColumns('desktop'),
    )
    setQuery((current) =>
      current.size === initialPageSize
        ? { ...current, page: 1, size: preferenceQuery.data.asset_list_page_size }
        : current,
    )
  }, [availableColumns, preferenceQuery.data])

  const assetsQuery = useQuery({
    queryKey: ['assets', 'list', query, queryRevision],
    queryFn: () => listAssets(query),
  })

  const referenceQuery = useQuery({
    queryKey: ['asset-form', 'references'],
    queryFn: loadAssetReferences,
    enabled: batchEditOpen || handoverOpen,
  })

  const selectedAssets = useMemo(
    () => (assetsQuery.data?.records ?? []).filter((asset) => selectedRowKeys.includes(asset.id)),
    [assetsQuery.data?.records, selectedRowKeys],
  )
  useEffect(() => {
    if (!batchEditOpen || selectedAssets.length !== 1) return
    let cancelled = false
    void getAsset(selectedAssets[0].id)
      .then((detail) => {
        if (cancelled) return
        batchForm.setFieldsValue({
          category_id: detail.category_id,
          unit_id: detail.unit_id,
          source_id: detail.source_id,
          location_id: detail.location_id,
          manager_id: detail.manager_id,
          supplier_id: detail.supplier_id,
          holder_user_id: detail.holder_user_id,
          usage_department_id: detail.usage_department_id,
          public_object_id: detail.public_object_id,
          remark: detail.remark,
        })
      })
      .catch((error: unknown) => {
        if (!cancelled)
          void message.error(error instanceof Error ? error.message : '资产信息加载失败')
      })
    return () => {
      cancelled = true
    }
  }, [batchEditOpen, batchForm, selectedAssets])

  const publicObjectQuery = useQuery({
    queryKey: ['public-usage-objects', 'asset-list-edit-enabled'],
    queryFn: () => assetManagementApi.publicObjects(false),
    enabled: batchEditOpen && selectedRowKeys.length === 1,
    staleTime: 60_000,
  })

  const exportJobsQuery = useQuery({
    queryKey: ['asset-exports'],
    queryFn: exportsApi.page,
    enabled: exportJobsOpen,
  })

  const createExportMutation = useMutation({
    mutationFn: exportsApi.create,
    onSuccess: async (job) => {
      await message.success(
        `已生成 ${job.item_count} 件资产的${job.job_type === 'ASSET_CSV' ? '台账' : '条码标签'}`,
      )
      setExportJobsOpen(true)
      void queryClient.invalidateQueries({ queryKey: ['asset-exports'] })
    },
    onError: (error: Error) => void message.error(error.message),
  })

  const downloadExportMutation = useMutation({
    mutationFn: exportsApi.download,
    onSuccess: () => void message.success('文件已开始下载'),
    onError: (error: Error) => void message.error(error.message),
  })
  const openLabelPdfMutation = useMutation({
    mutationFn: async ({
      assetIds,
      previewWindow,
    }: {
      assetIds: number[]
      previewWindow: Window | null
    }) => {
      const fallbackWindow = previewWindow ?? window.open('', '_blank')
      try {
        const qrBaseUrl = `${window.location.origin}${import.meta.env.BASE_URL}`.replace(/\/$/, '')
        const blob = await http.getBlob('/exports/labels', {
          params: { asset_ids: assetIds, base_url: qrBaseUrl },
          paramsSerializer: { indexes: null },
        })
        const url = URL.createObjectURL(blob)
        window.setTimeout(() => URL.revokeObjectURL(url), 10 * 60 * 1000)
        return { url, previewWindow: fallbackWindow }
      } catch (error) {
        fallbackWindow?.close()
        throw error
      }
    },
    onSuccess: ({ url, previewWindow }) => {
      if (previewWindow) {
        previewWindow.location.replace(url)
      } else {
        void message.error('浏览器拦截了预览窗口，请允许新窗口后重试')
      }
    },
    onError: (error: Error) => {
      void message.error(error.message || '条码标签 PDF 打开失败')
    },
  })
  const batchMutation = useMutation({
    mutationFn: async (values: BatchEditFormValues) => {
      const selected = (assetsQuery.data?.records ?? []).filter((asset) =>
        selectedRowKeys.includes(asset.id),
      )
      if (!selected.length) throw new Error('请先选择要修改的资产')
      const changes: Record<string, string | number | null> = {}
      if (selected.length === 1) {
        // Single-asset editing always submits the complete ownership tuple. This
        // makes clearing any field unambiguous for the backend: `null` means
        // clear it, while omitted fields would mean "keep the original value".
        changes.holder_user_id = values.holder_user_id ?? null
        changes.public_object_id = values.public_object_id ?? null
        changes.usage_department_id = values.usage_department_id ?? null
      }
      const fieldNames = [
        'category_id',
        'unit_id',
        'source_id',
        'location_id',
        'manager_id',
        'supplier_id',
      ] as const
      fieldNames.forEach((field) => {
        if (values[field] !== undefined) changes[field] = values[field] ?? null
      })
      if (values.remark !== undefined) changes.remark = values.remark.trim() || null
      if (!Object.keys(changes).length) throw new Error('请至少选择一个要修改的字段')
      return assetManagementApi.batchUpdate({
        items: selected.map((asset) => ({ asset_id: asset.id, version: asset.version })),
        changes,
        reason: values.reason,
      })
    },
    onSuccess: async (result) => {
      await message.success(`已更新 ${result.updated_count} 件资产`)
      setBatchEditOpen(false)
      setSelectedRowKeys([])
      batchForm.resetFields()
      void queryClient.invalidateQueries({ queryKey: ['assets'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error: Error) => void message.error(error.message),
  })

  const createHandoverMutation = useMutation({
    mutationFn: async (values: { reason?: string }) => {
      const selected = (assetsQuery.data?.records ?? []).filter((asset) =>
        selectedRowKeys.includes(asset.id),
      )
      if (!selected.length) throw new Error('请先选择要交接的资产')
      const invalidAsset = selected.find(
        (asset) => asset.status !== 'IDLE' && asset.status !== 'IN_USE',
      )
      if (invalidAsset) {
        throw new Error(`资产 ${invalidAsset.asset_code} 当前状态不允许交接`)
      }
      return assetManagementApi.transferHandover({
        items: selected.map((asset) => ({ asset_id: asset.id, version: asset.version })),
        reason: values.reason?.trim() || '资产台账发起扫码交接',
      })
    },
    onSuccess: async (result) => {
      if (!result.handover_token) throw new Error('交接二维码生成失败')
      setHandoverResult({
        handoverNo: result.handover_no,
        handoverToken: result.handover_token,
        assetCount: result.items.length,
      })
      await queryClient.invalidateQueries({ queryKey: ['transfer-handovers'] })
    },
    onError: (error: Error) => void message.error(error.message || '交接单创建失败'),
  })

  const selectedAssetIds = selectedRowKeys.map((key) => Number(key))

  const personalReturnMutation = useMutation({
    mutationFn: () =>
      assetUsageReturnApi.submit({
        action: 'PERSONAL_RETURN',
        asset_ids: selectedAssetIds,
      }),
    onSuccess: async (result) => {
      setReturnConfirmOpen(false)
      setSelectedRowKeys([])
      await message.success(`退库申请已提交，单号 ${result.request_no}`)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['assets'] }),
        queryClient.invalidateQueries({ queryKey: ['operation-requests'] }),
        queryClient.invalidateQueries({ queryKey: ['asset-usage', 'my-assets'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['workbench'] }),
        queryClient.invalidateQueries({ queryKey: ['todo-center'] }),
      ])
    },
    onError: (error: Error) => void message.error(error.message || '退库申请提交失败'),
  })

  const openReturnConfirm = () => {
    const invalidAsset = selectedAssets.find(
      (asset) =>
        asset.status !== 'IN_USE' ||
        asset.usage_type !== 'PERSONAL' ||
        asset.holder_user_id !== currentUserId ||
        asset.public_object_id != null,
    )
    if (invalidAsset) {
      void message.warning('仅本人个人领用且在用的资产可发起退库')
      return
    }
    setReturnConfirmOpen(true)
  }

  const exportCurrentResult = () => {
    createExportMutation.mutate({
      job_type: 'ASSET_CSV',
      filters: assetQueryToExportFilters(query),
    })
  }

  const exportSelected = (jobType: 'ASSET_CSV' | 'LABEL_PDF') => {
    if (!selectedAssetIds.length) {
      void message.warning('请先选择资产')
      return
    }
    if (jobType === 'LABEL_PDF') {
      const previewWindow = window.open('', '_blank')
      openLabelPdfMutation.mutate({ assetIds: selectedAssetIds, previewWindow })
      return
    }
    createExportMutation.mutate({ job_type: jobType, asset_ids: selectedAssetIds })
  }

  const handleSearch = () => {
    setSelectedRowKeys([])
    setQuery(buildAssetListQuery(draft, query.size))
    setQueryRevision(getNextQueryRevision)
  }

  const resetSearch = () => {
    setDraft(emptyFilters)
    setAssetCodesText('')
    setSelectedRowKeys([])
    setQuery(buildAssetListQuery(emptyFilters, query.size))
  }

  const toggleMyAssets = () => {
    setSelectedRowKeys([])
    setDraft((current) => {
      const next = { ...current, only_my_assets: !current.only_my_assets }
      setQuery(buildAssetListQuery(next, query.size))
      setQueryRevision(getNextQueryRevision)
      return next
    })
  }

  const openAssetCodes = () => {
    setAssetCodesText(draft.assetCodesText ?? '')
    setAssetCodesOpen(true)
  }

  const confirmAssetCodes = () => {
    setDraft((current) => ({ ...current, assetCodesText }))
    setAssetCodesOpen(false)
  }

  const updateTextFilter = (
    key:
      | 'company_name'
      | 'category_name'
      | 'department_name'
      | 'location_name'
      | 'user_name'
      | 'manager_name'
      | 'supplier_name'
      | 'source_name',
    value: string,
  ) => {
    setDraft((current) => ({ ...current, [key]: value }))
  }

  const handlePageChange = (page: number, size: number) => {
    const nextSize = size === 20 || size === 100 ? size : 50
    if (nextSize !== query.size) {
      preferenceMutation.mutate({ asset_list_page_size: nextSize })
    }
    setSelectedRowKeys([])
    setQuery((current) => ({
      ...current,
      page: nextSize === current.size ? page : 1,
      size: nextSize,
    }))
  }

  const handleColumnChange = (values: AssetColumnKey[]) => {
    if (!values.length) {
      void message.warning('至少保留一个资产列表字段')
      return
    }
    setSelectedColumns(values)
    preferenceMutation.mutate({ asset_list_columns: values })
  }

  const restoreDefaultColumns = () => {
    const defaults = getDefaultColumns('desktop').filter((column) =>
      availableColumns.includes(column),
    )
    setSelectedColumns(defaults)
    preferenceMutation.mutate({ asset_list_columns: defaults })
  }

  const columnDefinitions = useMemo<Record<AssetColumnKey, ColumnType<AssetSummary>>>(() => {
    const statusColumn: ColumnType<AssetSummary> = {
      title: t('assets.list.columns.status'),
      dataIndex: 'status',
      width: 108,
      render: (status: AssetStatus) => {
        const meta = getAssetStatusMeta(status)
        return <span className={`asset-list__status is-${meta.tone}`}>{t(meta.labelKey)}</span>
      },
    }

    return {
      asset_code: {
        title: t('assets.list.columns.asset_code'),
        dataIndex: 'asset_code',
        width: 142,
        render: (value: string, asset) => (
          <Link className="asset-list__record-link" to={`/assets/${asset.id}`}>
            {value}
          </Link>
        ),
      },
      asset_name: {
        title: t('assets.list.columns.asset_name'),
        dataIndex: 'asset_name',
        width: 200,
        render: (value: string, asset) => (
          <Link className="asset-list__asset-name" to={`/assets/${asset.id}`}>
            {value}
          </Link>
        ),
      },
      category_name: {
        title: t('assets.list.columns.category_name'),
        dataIndex: 'category_name',
        width: 120,
      },
      status: statusColumn,
      model: {
        title: t('assets.list.columns.model'),
        dataIndex: 'model',
        width: 180,
        render: valueOrDash,
      },
      serial_number: {
        title: t('assets.list.columns.serial_number'),
        dataIndex: 'serial_number',
        width: 160,
        render: valueOrDash,
      },
      receipt_number: {
        title: t('assets.list.columns.receipt_number'),
        dataIndex: 'receipt_number',
        width: 168,
        render: valueOrDash,
      },
      user_name: {
        title: t('assets.list.columns.user_name'),
        dataIndex: 'user_name',
        width: 110,
        render: valueOrDash,
      },
      department_name: {
        title: t('assets.list.columns.department_name'),
        dataIndex: 'department_name',
        width: 132,
        render: valueOrDash,
      },
      location_name: {
        title: t('assets.list.columns.location_name'),
        dataIndex: 'location_name',
        width: 220,
        render: (value: string) => <span className="asset-list__location">{value}</span>,
      },
      manager_name: {
        title: t('assets.list.columns.manager_name'),
        dataIndex: 'manager_name',
        width: 120,
        render: valueOrDash,
      },
      company_name: {
        title: t('assets.list.columns.company_name'),
        dataIndex: 'company_name',
        width: 220,
      },
      usage_company_name: {
        title: t('assets.list.columns.usage_company_name'),
        dataIndex: 'usage_company_name',
        width: 220,
        render: valueOrDash,
      },
      usage_department_name: {
        title: t('assets.list.columns.usage_department_name'),
        dataIndex: 'usage_department_name',
        width: 160,
        render: valueOrDash,
      },
      supplier_name: {
        title: t('assets.list.columns.supplier_name'),
        dataIndex: 'supplier_name',
        width: 220,
      },
      source_name: {
        title: t('assets.list.columns.source_name'),
        dataIndex: 'source_name',
        width: 112,
      },
      unit_name: {
        title: t('assets.list.columns.unit_name'),
        dataIndex: 'unit_name',
        width: 104,
      },
      purchase_date: {
        title: t('assets.list.columns.purchase_date'),
        dataIndex: 'purchase_date',
        width: 124,
        render: (value: string) => formatAssetDate(value, locale),
      },
      purchase_amount: {
        title: t('assets.list.columns.purchase_amount'),
        dataIndex: 'purchase_amount',
        align: 'right',
        width: 128,
        render: (value: number) => formatAssetAmount(value, locale),
      },
      information_complete: {
        title: t('assets.list.columns.information_complete'),
        dataIndex: 'information_complete',
        width: 116,
        render: (complete: boolean) =>
          complete ? t('assets.list.filters.complete') : t('assets.list.filters.incomplete'),
      },
    }
  }, [locale, t])

  const columns = useMemo<ColumnsType<AssetSummary>>(
    () =>
      selectedColumns
        .filter((column) => availableColumns.includes(column))
        .map((column) => columnDefinitions[column]),
    [availableColumns, columnDefinitions, selectedColumns],
  )

  const rowSelection: TableRowSelection<AssetSummary> = {
    selectedRowKeys,
    onChange: setSelectedRowKeys,
  }

  const purchaseDateRange: [Dayjs | null, Dayjs | null] | null =
    draft.purchase_date_from && draft.purchase_date_to
      ? [dayjs(draft.purchase_date_from), dayjs(draft.purchase_date_to)]
      : null

  const columnSettings = (
    <div className="asset-list__column-settings">
      <div className="asset-list__column-settings-heading">
        <span>显示列会按当前账号保存</span>
        <Button
          type="link"
          size="small"
          loading={preferenceMutation.isPending}
          onClick={restoreDefaultColumns}
        >
          恢复默认
        </Button>
      </div>
      <Checkbox.Group<AssetColumnKey>
        value={selectedColumns}
        options={availableColumns.map((column) => ({
          value: column,
          label: t(`assets.list.columns.${column}`),
        }))}
        onChange={handleColumnChange}
      />
    </div>
  )

  const renderResults = () => {
    if (assetsQuery.isPending) {
      return (
        <div
          className="asset-list__loading"
          role="status"
          aria-live="polite"
          aria-label={t('assets.list.loading')}
          aria-busy="true"
        >
          {isMobile ? (
            <div className="asset-list__loading-mobile" aria-hidden="true">
              {loadingCards.map((card) => (
                <div key={card} className="asset-list__loading-card">
                  <span className="asset-list__loading-check">
                    <Skeleton.Avatar active shape="square" size={18} />
                  </span>
                  <div className="asset-list__loading-card-body">
                    <div className="asset-list__loading-card-topline">
                      <Skeleton.Input active size="small" style={{ width: 96 }} />
                      <Skeleton.Input active size="small" style={{ width: 58 }} />
                    </div>
                    <div className="asset-list__loading-card-title">
                      <Skeleton.Input active block size="small" />
                    </div>
                    <div className="asset-list__loading-card-meta">
                      <Skeleton.Input active size="small" style={{ width: 82 }} />
                      <Skeleton.Input active size="small" style={{ width: 82 }} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="asset-list__loading-desktop" aria-hidden="true">
              <div className="asset-list__loading-table-head">
                {loadingColumns.map((column) => (
                  <span key={column}>
                    <Skeleton.Input active block size="small" />
                  </span>
                ))}
              </div>
              {loadingRows.map((row) => (
                <div key={row} className="asset-list__loading-table-row">
                  {loadingColumns.map((column) => (
                    <span key={column}>
                      <Skeleton.Input active block size="small" />
                    </span>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      )
    }

    if (assetsQuery.isError) {
      return (
        <StatePanel
          mode="error"
          message={t('assets.list.error')}
          retryLabel={t('common.retry')}
          onRetry={() => void assetsQuery.refetch()}
        />
      )
    }

    const result = assetsQuery.data
    if (result.records.length === 0) {
      return <StatePanel mode="empty" message={t('assets.list.empty')} />
    }

    return (
      <>
        {isMobile ? (
          <div className="asset-list__mobile">
            {result.records.map((asset) => {
              const statusMeta = getAssetStatusMeta(asset.status)
              const checked = selectedRowKeys.includes(asset.id)
              return (
                <article key={asset.id} className="asset-list__mobile-card">
                  <div className="asset-list__mobile-select">
                    <Checkbox
                      checked={checked}
                      aria-label={asset.asset_code}
                      onChange={(event) => {
                        setSelectedRowKeys((current) =>
                          event.target.checked
                            ? current.concat(asset.id)
                            : current.filter((key) => key !== asset.id),
                        )
                      }}
                    />
                  </div>
                  <Link className="asset-list__mobile-main" to={`/assets/${asset.id}`}>
                    <span className="asset-list__mobile-topline">
                      <span>{asset.asset_code}</span>
                      <span className={`asset-list__status is-${statusMeta.tone}`}>
                        {t(statusMeta.labelKey)}
                      </span>
                    </span>
                    <strong>{asset.asset_name}</strong>
                    <span className="asset-list__mobile-meta">
                      <span>{asset.category_name}</span>
                      <span>{asset.user_name || asset.location_name}</span>
                    </span>
                    {asset.user_name ? (
                      <span className="asset-list__mobile-location">{asset.location_name}</span>
                    ) : null}
                  </Link>
                </article>
              )
            })}
          </div>
        ) : (
          <div className="asset-list__desktop">
            <Table<AssetSummary>
              columns={columns}
              dataSource={result.records}
              pagination={false}
              rowKey="id"
              rowSelection={rowSelection}
              scroll={{ x: 1420 }}
            />
          </div>
        )}

        <div className="asset-list__pagination">
          <span>{t('assets.list.pagination.total', { total: result.total })}</span>
          <Pagination
            current={result.page}
            pageSize={result.size}
            pageSizeOptions={[20, 50, 100]}
            showSizeChanger
            showTotal={(total) => t('assets.list.pagination.total', { total })}
            total={result.total}
            onChange={handlePageChange}
          />
        </div>
      </>
    )
  }

  return (
    <div className="asset-list">
      <PageHeader
        title={t('assets.list.title')}
        description={t('assets.list.description')}
        actions={
          canCreate || canExport || canPrintLabels || canTransferHandover ? (
            <div className="asset-list__header-actions">
              {canExport || canPrintLabels ? (
                <Button
                  icon={<History aria-hidden="true" size={16} />}
                  onClick={() => setExportJobsOpen(true)}
                >
                  导出任务
                </Button>
              ) : null}
              {canExport ? (
                <Button
                  icon={<Download aria-hidden="true" size={16} />}
                  loading={createExportMutation.isPending}
                  onClick={exportCurrentResult}
                >
                  导出当前结果
                </Button>
              ) : null}
              {canTransferHandover ? (
                <Button
                  icon={<UserRoundCog aria-hidden="true" size={16} />}
                  onClick={() => {
                    if (!selectedRowKeys.length) {
                      void message.warning('请先选择要交接的资产')
                      return
                    }
                    handoverForm.resetFields()
                    setHandoverResult(null)
                    setHandoverOpen(true)
                  }}
                >
                  交接资产
                </Button>
              ) : null}
              {canCreate ? (
                <Link className="asset-list__create-link" to="/assets/new">
                  <Plus aria-hidden="true" size={17} />
                  <span>{t('assets.list.actions.create')}</span>
                </Link>
              ) : null}
            </div>
          ) : undefined
        }
      />

      <section className="asset-list__filter-panel" aria-label={t('assets.list.title')}>
        <form
          onSubmit={(event) => {
            event.preventDefault()
            handleSearch()
          }}
        >
          <div className="asset-list__search-row">
            <Input
              allowClear
              prefix={<Search aria-hidden="true" size={17} />}
              value={draft.keyword ?? ''}
              aria-label={t('assets.list.filters.keyword')}
              placeholder={t('assets.list.filters.keywordPlaceholder')}
              onChange={(event) =>
                setDraft((current) => ({ ...current, keyword: event.target.value }))
              }
            />
            <Button icon={<ListFilter aria-hidden="true" size={17} />} onClick={openAssetCodes}>
              {t('assets.list.actions.assetCodes')}
            </Button>
            <Button type="primary" htmlType="submit" icon={<Search aria-hidden="true" size={17} />}>
              {t('assets.list.actions.search')}
            </Button>
          </div>

          <div className="asset-list__common-filters">
            {commonTextFilters.map((filter) => (
              <Input
                key={filter.key}
                allowClear
                value={draft[filter.key] ?? ''}
                aria-label={t(filter.labelKey)}
                placeholder={t(filter.labelKey)}
                onChange={(event) => updateTextFilter(filter.key, event.target.value)}
              />
            ))}
            <Select
              allowClear
              value={draft.status}
              aria-label={t('assets.list.filters.status')}
              placeholder={t('assets.list.filters.status')}
              options={statusOptions.map((option) => ({
                value: option.value,
                label: t(option.meta.labelKey),
              }))}
              onChange={(status: AssetStatus | undefined) =>
                setDraft((current) => ({ ...current, status }))
              }
            />
            <Select
              allowClear
              value={draft.information_complete}
              aria-label={t('assets.list.filters.informationComplete')}
              placeholder={t('assets.list.filters.informationComplete')}
              options={[
                { value: true, label: t('assets.list.filters.complete') },
                { value: false, label: t('assets.list.filters.incomplete') },
              ]}
              onChange={(informationComplete: boolean | undefined) =>
                setDraft((current) => ({
                  ...current,
                  information_complete: informationComplete,
                }))
              }
            />
          </div>

          <div className="asset-list__filter-actions">
            {canViewAllAssets ? (
              <Button
                type={draft.only_my_assets ? 'primary' : 'default'}
                aria-pressed={draft.only_my_assets}
                onClick={toggleMyAssets}
              >
                {draft.only_my_assets ? '显示全部资产' : '显示我名下资产'}
              </Button>
            ) : null}
            <Button
              icon={<SlidersHorizontal aria-hidden="true" size={17} />}
              onClick={() => setMoreFiltersOpen(true)}
            >
              {t('assets.list.actions.moreFilters')}
            </Button>
            <Popover
              content={columnSettings}
              placement="bottomRight"
              trigger="click"
              title={t('assets.list.actions.columnSettings')}
            >
              <Button icon={<Columns3 aria-hidden="true" size={17} />}>
                {t('assets.list.actions.columnSettings')}
              </Button>
            </Popover>
            <Button icon={<RotateCcw aria-hidden="true" size={17} />} onClick={resetSearch}>
              {t('assets.list.actions.reset')}
            </Button>
          </div>
        </form>
      </section>

      {selectedRowKeys.length > 0 ? (
        <div className="asset-list__selection-bar" role="status">
          <span>{t('assets.list.selection.selected', { count: selectedRowKeys.length })}</span>
          <div>
            <Button type="link" onClick={() => setSelectedRowKeys([])}>
              {t('assets.list.selection.clear')}
            </Button>
            {canExport ? (
              <Button
                icon={<FileSpreadsheet aria-hidden="true" size={16} />}
                loading={createExportMutation.isPending}
                onClick={() => exportSelected('ASSET_CSV')}
              >
                导出所选
              </Button>
            ) : null}
            {canPrintLabels ? (
              <Button
                icon={<Printer aria-hidden="true" size={16} />}
                loading={createExportMutation.isPending || openLabelPdfMutation.isPending}
                onClick={() => exportSelected('LABEL_PDF')}
              >
                条码标签 PDF
              </Button>
            ) : null}
            {canSelfReturn ? (
              <Button
                type={canExport || canPrintLabels ? 'default' : 'primary'}
                icon={<PackageMinus aria-hidden="true" size={16} />}
                onClick={openReturnConfirm}
              >
                退库申请
              </Button>
            ) : null}
            {(permissions?.includes('asset:edit') ?? false) ? (
              <Button
                type="primary"
                icon={<PencilLine aria-hidden="true" size={16} />}
                onClick={() => {
                  batchForm.resetFields()
                  const currentAsset =
                    selectedRowKeys.length === 1
                      ? ((assetsQuery.data?.records ?? []).find(
                          (item) => item.id === selectedRowKeys[0],
                        ) ?? null)
                      : null
                  setBatchEditAsset(currentAsset)
                  setBatchEditOpen(true)
                }}
              >
                {selectedRowKeys.length === 1 ? '编辑' : '批量编辑'}
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}

      <section className="asset-list__results">{renderResults()}</section>

      <Modal
        className="asset-list__modal"
        open={handoverOpen}
        title={handoverResult ? '交接二维码已生成' : '发起资产交接'}
        okText={handoverResult ? '完成' : '生成交接二维码'}
        cancelText={handoverResult ? '关闭' : '取消'}
        confirmLoading={createHandoverMutation.isPending}
        afterClose={() => createHandoverMutation.reset()}
        onOk={() => {
          if (handoverResult) {
            setHandoverOpen(false)
            setSelectedRowKeys([])
            return
          }
          void handoverForm.submit()
        }}
        onCancel={() => setHandoverOpen(false)}
        footer={handoverResult ? null : undefined}
      >
        {handoverResult ? (
          <div className="asset-list__handover-result">
            <div className="asset-list__handover-meta">
              <strong>{handoverResult.handoverNo}</strong>
              <span>共 {handoverResult.assetCount} 件资产</span>
            </div>
            <QRCode
              size={216}
              errorLevel="M"
              value={`${window.location.origin}${import.meta.env.BASE_URL}asset-transfer?handover_token=${handoverResult.handoverToken}&handover_no=${encodeURIComponent(handoverResult.handoverNo)}`}
            />
            <div className="asset-list__handover-tip">
              接收员工在「业务流程 → 扫码领用 / 借用」中扫描此二维码，确认后即完成交接。
            </div>
            <Button
              type="primary"
              block
              onClick={() => {
                setHandoverOpen(false)
                setSelectedRowKeys([])
              }}
            >
              完成
            </Button>
          </div>
        ) : (
          <Form
            form={handoverForm}
            layout="vertical"
            onFinish={(values) => createHandoverMutation.mutate(values)}
          >
            <div className="asset-list__batch-note">
              将为已选择的 {selectedRowKeys.length} 件生成交接二维码，接收人扫码确认后变为使用人。
            </div>
            <Form.Item
              name="reason"
              label="交接原因"
              rules={[{ required: true, whitespace: true, message: '请填写交接原因' }]}
            >
              <Input.TextArea
                rows={3}
                maxLength={200}
                showCount
                placeholder="例如：设备责任人调整"
              />
            </Form.Item>
            <Button htmlType="submit" className="asset-list__hidden-submit" aria-hidden="true">
              提交
            </Button>
          </Form>
        )}
      </Modal>

      <Modal
        className="asset-list__modal"
        open={returnConfirmOpen}
        title="提交个人退库申请"
        okText="提交退库申请"
        cancelText="取消"
        confirmLoading={personalReturnMutation.isPending}
        onOk={() => personalReturnMutation.mutate()}
        onCancel={() => setReturnConfirmOpen(false)}
      >
        <div className="asset-list__batch-note">
          将提交 {selectedAssets.length} 件本人资产的个人退库申请，提交后等待管理员验收。
        </div>
        <ul className="asset-list__return-preview">
          {selectedAssets.map((asset) => (
            <li key={asset.id}>
              <strong>{asset.asset_name}</strong>
              <span>{asset.asset_code}</span>
            </li>
          ))}
        </ul>
      </Modal>

      <Modal
        className="asset-list__modal"
        open={assetCodesOpen}
        title={t('assets.list.filters.assetCodes')}
        okText={t('assets.list.selection.confirm')}
        cancelText={t('assets.list.selection.cancel')}
        onOk={confirmAssetCodes}
        onCancel={() => setAssetCodesOpen(false)}
      >
        <Input.TextArea
          autoSize={{ minRows: 7, maxRows: 14 }}
          value={assetCodesText}
          aria-label={t('assets.list.filters.assetCodes')}
          placeholder={t('assets.list.filters.assetCodesPlaceholder')}
          onChange={(event) => setAssetCodesText(event.target.value)}
        />
      </Modal>

      <Drawer
        rootClassName="asset-list__drawer"
        open={moreFiltersOpen}
        title={t('assets.list.actions.moreFilters')}
        width={400}
        onClose={() => setMoreFiltersOpen(false)}
      >
        <div className="asset-list__drawer-fields">
          {moreTextFilters.map((filter) => (
            <label key={filter.key}>
              <span>{t(filter.labelKey)}</span>
              <Input
                allowClear
                value={draft[filter.key] ?? ''}
                placeholder={t(filter.labelKey)}
                onChange={(event) => updateTextFilter(filter.key, event.target.value)}
              />
            </label>
          ))}
          <label>
            <span>{t('assets.list.filters.purchaseDate')}</span>
            <RangePicker
              value={purchaseDateRange}
              aria-label={t('assets.list.filters.purchaseDate')}
              placeholder={[
                t('assets.list.filters.purchaseDateFrom'),
                t('assets.list.filters.purchaseDateTo'),
              ]}
              onChange={(_, dateStrings) =>
                setDraft((current) => ({
                  ...current,
                  purchase_date_from: dateStrings[0] || undefined,
                  purchase_date_to: dateStrings[1] || undefined,
                }))
              }
            />
          </label>
        </div>
        <div className="asset-list__drawer-actions">
          <Button
            icon={<RotateCcw aria-hidden="true" size={17} />}
            onClick={() => {
              setDraft((current) => ({
                ...current,
                user_name: undefined,
                manager_name: undefined,
                supplier_name: undefined,
                source_name: undefined,
                purchase_date_from: undefined,
                purchase_date_to: undefined,
              }))
            }}
          >
            {t('assets.list.actions.reset')}
          </Button>
          <Button
            type="primary"
            icon={<Filter aria-hidden="true" size={17} />}
            onClick={() => {
              setMoreFiltersOpen(false)
              handleSearch()
            }}
          >
            {t('assets.list.actions.search')}
          </Button>
        </div>
      </Drawer>

      <Modal
        className="asset-list__modal asset-list__export-modal"
        open={exportJobsOpen}
        title="导出与标签任务"
        footer={null}
        width={760}
        onCancel={() => setExportJobsOpen(false)}
      >
        <div className="asset-list__export-intro">
          <div>
            <strong>服务端生成 · 24 小时有效</strong>
            <span>台账按当前账号的数据范围和金额权限生成；条码标签固定为 65 × 30 mm。</span>
          </div>
          <Button
            icon={<RotateCcw aria-hidden="true" size={16} />}
            loading={exportJobsQuery.isFetching}
            onClick={() => void exportJobsQuery.refetch()}
          >
            刷新
          </Button>
        </div>
        <div className="asset-list__export-scroll">
          {exportJobsQuery.isLoading ? (
            <Skeleton active paragraph={{ rows: 5 }} />
          ) : exportJobsQuery.isError ? (
            <StatePanel
              mode="error"
              message="导出任务加载失败"
              retryLabel="重新加载"
              onRetry={() => void exportJobsQuery.refetch()}
            />
          ) : exportJobsQuery.data?.items.length ? (
            <div className="asset-list__export-jobs">
              {exportJobsQuery.data.items.map((job) => {
                const status = exportStatusMeta[job.status]
                return (
                  <article key={job.id} className="asset-list__export-job">
                    <div className="asset-list__export-job-icon" aria-hidden="true">
                      {job.job_type === 'ASSET_CSV' ? (
                        <FileSpreadsheet size={20} />
                      ) : (
                        <Printer size={20} />
                      )}
                    </div>
                    <div className="asset-list__export-job-copy">
                      <div>
                        <strong>{job.original_name}</strong>
                        <span className={`asset-list__export-status is-${status.tone}`}>
                          {status.label}
                        </span>
                      </div>
                      <p>
                        {job.item_count} 件 · {formatBytes(job.size_bytes)} · 创建于{' '}
                        {dayjs(job.created_at).format('YYYY-MM-DD HH:mm')}
                      </p>
                      <span>
                        <Clock3 aria-hidden="true" size={13} />
                        有效至 {dayjs(job.expires_at).format('YYYY-MM-DD HH:mm')}
                      </span>
                      {job.error_message ? <em>{job.error_message}</em> : null}
                    </div>
                    <Button
                      type="primary"
                      icon={<Download aria-hidden="true" size={16} />}
                      disabled={job.status !== 'SUCCESS'}
                      loading={
                        downloadExportMutation.isPending &&
                        downloadExportMutation.variables?.id === job.id
                      }
                      onClick={() => downloadExportMutation.mutate(job)}
                    >
                      下载
                    </Button>
                  </article>
                )
              })}
            </div>
          ) : (
            <StatePanel mode="empty" message="还没有导出任务，可从资产列表生成台账或条码标签。" />
          )}
        </div>
      </Modal>

      <Modal
        className="asset-list__modal asset-list__batch-modal"
        open={batchEditOpen}
        title={
          selectedRowKeys.length === 1 && batchEditAsset?.asset_name
            ? `编辑 · ${batchEditAsset.asset_name}`
            : selectedRowKeys.length === 1
              ? `编辑 ${selectedRowKeys.length} 件资产`
              : `批量编辑 ${selectedRowKeys.length} 件资产`
        }
        okText="确认批量修改"
        cancelText="取消"
        width={680}
        confirmLoading={batchMutation.isPending}
        onOk={() => batchForm.submit()}
        onCancel={() => setBatchEditOpen(false)}
      >
        <p className="asset-list__batch-note">
          只填写需要修改的字段；未填写的字段会保持原值。添加使用人、使用部门或公共使用对象后，资产会自动转为「在用」，无需再选择状态和使用方式。
        </p>
        <Form
          form={batchForm}
          layout="vertical"
          className="asset-list__batch-form"
          onFinish={(values) => batchMutation.mutate(values)}
        >
          <div className="asset-list__batch-grid">
            <Form.Item name="category_id" label="资产分类">
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                loading={referenceQuery.isLoading}
                options={flattenTree(referenceQuery.data?.categories ?? []).map((item) => ({
                  value: item.id,
                  label: `${item.name} · ${item.code}`,
                }))}
                placeholder="保持原分类"
              />
            </Form.Item>
            <Form.Item name="unit_id" label="计量单位">
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                loading={referenceQuery.isLoading}
                options={(referenceQuery.data?.units ?? []).map((item) => ({
                  value: item.id,
                  label: `${item.name} · ${item.code}`,
                }))}
                placeholder="保持原单位"
              />
            </Form.Item>
            <Form.Item name="source_id" label="资产来源">
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                loading={referenceQuery.isLoading}
                options={(referenceQuery.data?.sources ?? []).map((item) => ({
                  value: item.id,
                  label: `${item.name} · ${item.code}`,
                }))}
                placeholder="保持原来源"
              />
            </Form.Item>
            <Form.Item name="location_id" label="存放地点">
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                loading={referenceQuery.isLoading}
                options={flattenTree(referenceQuery.data?.locations ?? []).map((item) => ({
                  value: item.id,
                  label: `${item.name} · ${item.code}`,
                }))}
                placeholder="保持原地点"
              />
            </Form.Item>
            <Form.Item name="manager_id" label="责任管理员">
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                loading={referenceQuery.isLoading}
                options={(referenceQuery.data?.managers ?? [])
                  .filter((item) => item.enabled)
                  .map((item) => ({ value: item.id, label: item.name }))}
                placeholder="保持原管理员"
              />
            </Form.Item>
            <Form.Item name="supplier_id" label="供应商">
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                loading={referenceQuery.isLoading}
                options={(referenceQuery.data?.suppliers ?? []).map((item) => ({
                  value: item.id,
                  label: `${item.name} · ${item.code}`,
                }))}
                placeholder="保持原供应商"
              />
            </Form.Item>
            {selectedRowKeys.length === 1 ? (
              <>
                <Form.Item name="holder_user_id" label="使用人">
                  <Select
                    allowClear
                    showSearch
                    optionFilterProp="label"
                    loading={referenceQuery.isLoading}
                    options={(referenceQuery.data?.holders ?? []).map((item) => ({
                      value: item.id,
                      label: item.name,
                    }))}
                    placeholder="选择使用人后自动转为个人使用并在用"
                  />
                </Form.Item>
                <Form.Item name="usage_department_id" label="使用部门">
                  <Select
                    allowClear
                    showSearch
                    optionFilterProp="label"
                    loading={referenceQuery.isLoading}
                    options={flattenTree(referenceQuery.data?.organizations ?? []).map((item) => ({
                      value: item.id,
                      label: item.name,
                    }))}
                    placeholder="选择使用部门后自动转为在用"
                  />
                </Form.Item>
                <Form.Item name="public_object_id" label="公共使用对象">
                  <Select
                    allowClear
                    showSearch
                    optionFilterProp="label"
                    loading={publicObjectQuery.isLoading}
                    options={(publicObjectQuery.data ?? []).map((item) => ({
                      value: item.id,
                      label: `${item.name} · ${item.code}`,
                    }))}
                    placeholder="选择公共对象后自动转为公共使用并在用"
                  />
                </Form.Item>
              </>
            ) : null}
          </div>
          <Form.Item name="remark" label="统一备注">
            <Input.TextArea rows={3} maxLength={2000} showCount placeholder="不填写则保持原备注" />
          </Form.Item>
          <Form.Item
            name="reason"
            label="修改原因"
            rules={[{ required: true, whitespace: true, message: '请填写批量修改原因' }]}
          >
            <Input.TextArea
              rows={4}
              maxLength={500}
              showCount
              placeholder="该原因会写入每件资产的履历与审计日志"
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
