import { useQuery } from '@tanstack/react-query'
import {
  Button,
  Checkbox,
  DatePicker,
  Drawer,
  Input,
  Modal,
  Pagination,
  Popover,
  Select,
  Skeleton,
  Table,
} from 'antd'
import type { ColumnType, ColumnsType, TableRowSelection } from 'antd/es/table/interface'
import dayjs from 'dayjs'
import type { Dayjs } from 'dayjs'
import {
  Columns3,
  Filter,
  ListFilter,
  Plus,
  RotateCcw,
  Search,
  SlidersHorizontal,
} from 'lucide-react'
import type { Key } from 'react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { listAssets } from '@/api/assets'
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

function valueOrDash(value: string | undefined): string {
  return value || '—'
}

export default function AssetList() {
  const { i18n, t } = useTranslation()
  const isMobile = useMobileViewport()
  const permissions = useAuthStore((state) => state.user?.permissions)
  const canCreate = canCreateAsset(permissions)
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
  const [selectAllOpen, setSelectAllOpen] = useState(false)
  const [queryRevision, setQueryRevision] = useState(0)

  const assetsQuery = useQuery({
    queryKey: ['assets', 'list', query, queryRevision],
    queryFn: () => listAssets(query),
  })

  const handleSearch = () => {
    setSelectedRowKeys([])
    setQuery(buildAssetListQuery(draft, query.size))
    setQueryRevision(getNextQueryRevision)
  }

  const resetSearch = () => {
    setDraft(emptyFilters)
    setAssetCodesText('')
    setSelectedRowKeys([])
    setQuery(buildAssetListQuery(emptyFilters, initialPageSize))
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
    setSelectedRowKeys([])
    setQuery((current) => ({
      ...current,
      page: nextSize === current.size ? page : 1,
      size: nextSize,
    }))
  }

  const handleColumnChange = (values: AssetColumnKey[]) => {
    setSelectedColumns(values)
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
          canCreate ? (
            <Link className="asset-list__create-link" to="/assets/new">
              <Plus aria-hidden="true" size={17} />
              <span>{t('assets.list.actions.create')}</span>
            </Link>
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
            <Button onClick={() => setSelectAllOpen(true)}>
              {t('assets.list.selection.selectAllFiltered')}
            </Button>
          </div>
        </div>
      ) : null}

      <section className="asset-list__results">{renderResults()}</section>

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
        className="asset-list__modal"
        open={selectAllOpen}
        title={t('assets.list.selection.confirmTitle')}
        okText={t('assets.list.selection.confirm')}
        cancelText={t('assets.list.selection.cancel')}
        onOk={() => setSelectAllOpen(false)}
        onCancel={() => setSelectAllOpen(false)}
      >
        <p>
          {t('assets.list.selection.confirmDescription', {
            total: assetsQuery.data?.total ?? 0,
          })}
        </p>
      </Modal>
    </div>
  )
}
