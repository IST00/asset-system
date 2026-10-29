import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { zodResolver } from '@hookform/resolvers/zod'
import { Modal, message } from 'antd'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import type { TreeItem } from '@/api/administration'
import {
  createAsset,
  getAsset,
  getStockInRequest,
  loadAssetReferences,
  resubmitAsset,
  updateAsset,
  type AssetReferenceData,
  type StockInRequestDetail,
  type StockInSubmitResult,
} from '@/api/assets'
import PageHeader from '@/components/ui/PageHeader'
import StatePanel from '@/components/ui/StatePanel'
import { canCreateAsset } from '@/features/assets/assetModel'
import type { AssetDetail, AssetFormValues } from '@/features/assets/types'
import { useAuthStore } from '@/store/auth'
import AssetFormLoading from './AssetFormLoading'
import AssetFormEditor from './AssetFormSections'
import type { AssetFormOptions } from './AssetFormSections'
import {
  assetFormDefaultValues,
  buildAssetFormPayload,
  canShowAssetAmount,
  getAssetDetailQueryKey,
  getAssetListQueryKey,
  shouldRetryAssetFormQuery,
  toAssetFormValues,
} from './formModel'
import { assetFormSchema, getAssetFormMode } from './schema'
import type { AssetFormInput } from './schema'
import './AssetForm.css'

type SubmitResult =
  | { kind: 'asset'; asset: AssetDetail }
  | { kind: 'stock-in'; request: StockInSubmitResult; resubmitted: boolean }

type ResubmitPreparation = { values: AssetFormValues; error?: never } | { error: string }

const flattenTree = (items: TreeItem[]): TreeItem[] =>
  items.flatMap((item) => [item, ...flattenTree(item.children ?? [])])

const toOptions = (items: Array<{ name: string; status?: string; enabled?: boolean }>) =>
  items
    .filter((item) => item.enabled !== false && item.status !== 'DISABLED')
    .map((item) => ({ label: item.name, value: item.name }))

function buildOptions(references: AssetReferenceData): AssetFormOptions {
  const organizations = flattenTree(references.organizations)
  return {
    companies: toOptions(organizations),
    usageCompanies: toOptions(organizations),
    usageDepartments: toOptions(organizations),
    holders: toOptions(references.holders),
    holderDepartmentNames: Object.fromEntries(
      references.holders.map((holder) => [
        holder.name,
        organizationNameById(organizations, holder.organization_id),
      ]),
    ),
    categories: toOptions(flattenTree(references.categories)),
    sources: toOptions(references.sources),
    units: toOptions(references.units),
    suppliers: toOptions(references.suppliers),
    locations: toOptions(flattenTree(references.locations)),
    managers: toOptions(references.managers),
  }
}

function nameById<T extends { id: number; name: string }>(
  items: T[],
  id: number | null | undefined,
): string | undefined {
  if (id === null || id === undefined) return undefined
  return items.find((item) => item.id === id)?.name
}

function organizationNameById(items: TreeItem[], id: number | null | undefined): string {
  if (id === null || id === undefined) return ''
  return items.find((item) => item.id === id)?.name ?? ''
}

function prepareResubmit(
  request: StockInRequestDetail,
  references: AssetReferenceData,
): ResubmitPreparation {
  if (request.approval_status !== 'REJECTED') {
    return { error: '只有已拒绝的入库申请可以编辑后重新提交。' }
  }
  if (request.items.length !== 1) {
    return {
      error: '该申请包含多件资产，请前往导入中心重新生成整批申请，系统不会只重提其中一件。',
    }
  }
  const item = request.items[0]
  const organizations = flattenTree(references.organizations)
  const categories = flattenTree(references.categories)
  const locations = flattenTree(references.locations)
  const companyName = nameById(organizations, request.organization_id)
  const usageCompanyName = nameById(organizations, item.usage_company_id)
  const usageDepartmentName = nameById(organizations, item.usage_department_id)
  const categoryName = nameById(categories, item.category_id)
  const unitName = nameById(references.units, item.unit_id)
  const sourceName = nameById(references.sources, item.source_id)
  const locationName = nameById(locations, item.location_id)
  const managerName = nameById(references.managers, item.manager_id)
  const holderUserName = nameById(references.holders, item.holder_user_id)
  const supplierName = nameById(references.suppliers, item.supplier_id)
  const amount = item.original_amount === undefined ? Number.NaN : Number(item.original_amount)
  if (
    !companyName ||
    !usageCompanyName ||
    !categoryName ||
    !unitName ||
    !sourceName ||
    !locationName ||
    !managerName ||
    !Number.isFinite(amount)
  ) {
    return { error: '原申请引用的基础资料或金额已不可用，请联系管理员确认后再重新提交。' }
  }
  return {
    values: {
      asset_name: item.asset_name,
      company_name: companyName,
      usage_company_name: usageCompanyName,
      usage_department_name: usageDepartmentName ?? '',
      holder_user_name: holderUserName ?? '',
      category_name: categoryName,
      source_name: sourceName,
      unit_name: unitName,
      supplier_name: supplierName ?? '',
      purchase_date: item.purchase_date,
      location_name: locationName,
      purchase_amount: amount,
      zero_amount_reason: item.zero_amount_reason ?? '',
      model: item.specification_model ?? '',
      serial_number: item.serial_number ?? '',
      manager_name: managerName,
      rfid_tag: item.rfid_tag ?? '',
      change_reason: '',
      remark: item.remark ?? request.remark ?? '',
    },
  }
}

export default function AssetForm() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const permissions = useAuthStore((state) => state.user?.permissions)
  const [messageApi, messageContextHolder] = message.useMessage()
  const [modalApi, modalContextHolder] = Modal.useModal()
  const { assetId } = useParams<{ assetId: string }>()
  const [searchParams] = useSearchParams()
  const mode = getAssetFormMode(assetId)
  const editAssetId = mode?.mode === 'edit' ? mode.assetId : null
  const resubmitRaw = searchParams.get('resubmit')
  const parsedResubmitId = resubmitRaw && /^\d+$/.test(resubmitRaw) ? Number(resubmitRaw) : null
  const resubmitId =
    mode?.mode === 'create' && parsedResubmitId && Number.isSafeInteger(parsedResubmitId)
      ? parsedResubmitId
      : null
  const invalidResubmit = resubmitRaw !== null && resubmitId === null
  const isResubmit = resubmitId !== null
  const showAmount = mode ? canShowAssetAmount(mode.mode, permissions) : false
  const [submitFailed, setSubmitFailed] = useState(false)
  const {
    control,
    getValues,
    handleSubmit,
    reset,
    setValue,
    formState: { errors, isDirty },
  } = useForm<AssetFormInput>({
    resolver: zodResolver(assetFormSchema),
    defaultValues: assetFormDefaultValues,
  })

  const assetQuery = useQuery({
    queryKey: getAssetDetailQueryKey(editAssetId ?? 0),
    queryFn: () =>
      editAssetId === null ? Promise.reject(new Error('INVALID_ASSET_ID')) : getAsset(editAssetId),
    enabled: editAssetId !== null,
    retry: shouldRetryAssetFormQuery,
  })
  const stockInQuery = useQuery({
    queryKey: ['stock-in-request', resubmitId],
    queryFn: () =>
      resubmitId === null
        ? Promise.reject(new Error('INVALID_STOCK_IN_REQUEST_ID'))
        : getStockInRequest(resubmitId),
    enabled: resubmitId !== null,
    retry: false,
  })
  const referenceQuery = useQuery({
    queryKey: ['asset-form', 'references'],
    queryFn: loadAssetReferences,
    staleTime: 60_000,
  })
  const options = useMemo(
    () => (referenceQuery.data ? buildOptions(referenceQuery.data) : null),
    [referenceQuery.data],
  )
  const resubmitPreparation = useMemo(
    () =>
      stockInQuery.data && referenceQuery.data
        ? prepareResubmit(stockInQuery.data, referenceQuery.data)
        : null,
    [referenceQuery.data, stockInQuery.data],
  )

  useEffect(() => {
    if (assetQuery.data) reset(toAssetFormValues(assetQuery.data))
  }, [assetQuery.data, reset])

  useEffect(() => {
    if (resubmitPreparation && 'values' in resubmitPreparation) {
      reset(resubmitPreparation.values)
    }
  }, [reset, resubmitPreparation])

  const mutation = useMutation<SubmitResult, Error, AssetFormInput>({
    mutationFn: async (values) => {
      const references = referenceQuery.data
      if (!references) throw new Error('基础资料尚未加载完成')
      const payload = buildAssetFormPayload(
        values,
        mode?.mode === 'edit' && !showAmount && assetQuery.data
          ? {
              purchase_amount: assetQuery.data.purchase_amount,
              zero_amount_reason: assetQuery.data.zero_amount_reason,
            }
          : undefined,
      )
      if (mode?.mode === 'edit') {
        const current = assetQuery.data
        if (!current) throw new Error('资产资料尚未加载完成')
        if (!payload.change_reason?.trim()) throw new Error('请填写修改原因')
        return {
          kind: 'asset',
          asset: await updateAsset(mode.assetId, payload, current, references),
        }
      }
      if (mode?.mode === 'create' && resubmitId !== null) {
        const original = stockInQuery.data
        if (!original) throw new Error('原入库申请尚未加载完成')
        return {
          kind: 'stock-in',
          request: await resubmitAsset(resubmitId, payload, references, original),
          resubmitted: true,
        }
      }
      if (mode?.mode === 'create') {
        return {
          kind: 'stock-in',
          request: await createAsset(payload, references),
          resubmitted: false,
        }
      }
      throw new Error('资产地址无效')
    },
    onMutate: () => setSubmitFailed(false),
    onSuccess: async (result) => {
      void queryClient.invalidateQueries({ queryKey: getAssetListQueryKey() })
      void queryClient.invalidateQueries({ queryKey: ['operation-requests'] })
      if (result.kind === 'asset') {
        queryClient.setQueryData(getAssetDetailQueryKey(result.asset.id), result.asset)
        await messageApi.success({ content: t('assets.form.updateSuccess'), duration: 0.6 })
        navigate(`/assets/${result.asset.id}`)
        return
      }
      await messageApi.success({
        content: `${result.resubmitted ? '新一轮' : ''}入库申请 ${result.request.request_no} 已提交`,
        duration: 0.9,
      })
      navigate('/workflows')
    },
    onError: (error) => {
      setSubmitFailed(true)
      void messageApi.error(error.message)
    },
  })

  const cancel = () => {
    const goBack = () => navigate(-1)
    if (!isDirty) {
      goBack()
      return
    }

    modalApi.confirm({
      className: 'asset-form-unsaved-modal',
      title: t('assets.form.unsaved.title'),
      content: t('assets.form.unsaved.description'),
      okText: t('assets.form.unsaved.confirm'),
      cancelText: t('assets.form.unsaved.cancel'),
      okButtonProps: { danger: true },
      onOk: goBack,
    })
  }

  const renderWithContext = (page: ReactNode) => (
    <>
      {messageContextHolder}
      {modalContextHolder}
      {page}
    </>
  )

  if (mode === null || invalidResubmit) {
    return renderWithContext(
      <div className="asset-form">
        <StatePanel mode="empty" message={t('assets.detail.notFound')} />
      </div>,
    )
  }

  if (mode.mode === 'create' && !canCreateAsset(permissions)) {
    return renderWithContext(
      <div className="asset-form">
        <StatePanel mode="empty" message={t('assets.detail.notFound')} />
      </div>,
    )
  }

  if (
    (mode.mode === 'edit' && assetQuery.isLoading) ||
    (isResubmit && stockInQuery.isLoading) ||
    referenceQuery.isLoading
  ) {
    return renderWithContext(
      <div className="asset-form" aria-label={t('assets.form.loading')} aria-busy="true">
        <PageHeader
          title={
            isResubmit
              ? '编辑并重新提交入库申请'
              : t(mode.mode === 'edit' ? 'assets.form.editTitle' : 'assets.form.createTitle')
          }
          description={
            isResubmit
              ? '正在读取原申请和基础资料。'
              : t(
                  mode.mode === 'edit'
                    ? 'assets.form.editDescription'
                    : 'assets.form.createDescription',
                )
          }
        />
        <AssetFormLoading />
      </div>,
    )
  }

  const preparationError = resubmitPreparation && 'error' in resubmitPreparation
  if (
    (mode.mode === 'edit' && assetQuery.isError) ||
    (isResubmit && stockInQuery.isError) ||
    referenceQuery.isError ||
    !options ||
    preparationError
  ) {
    const notFound =
      assetQuery.error instanceof Error && assetQuery.error.message === 'ASSET_NOT_FOUND'
    const messageText = preparationError
      ? (resubmitPreparation?.error ?? '原入库申请无法重新提交。')
      : isResubmit
        ? '原入库申请不存在、无权查看或已无法重新提交。'
        : t(notFound ? 'assets.detail.notFound' : 'assets.form.errors.load')
    return renderWithContext(
      <div className="asset-form">
        <StatePanel
          mode={notFound || preparationError ? 'empty' : 'error'}
          message={messageText}
          retryLabel={notFound || preparationError ? undefined : t('assets.form.actions.retry')}
          onRetry={
            notFound || preparationError
              ? undefined
              : () => {
                  void assetQuery.refetch()
                  void stockInQuery.refetch()
                  void referenceQuery.refetch()
                }
          }
        />
      </div>,
    )
  }

  const asset = assetQuery.data
  const isEdit = mode.mode === 'edit'
  return renderWithContext(
    <div className="asset-form">
      <PageHeader
        title={
          isResubmit
            ? '编辑并重新提交入库申请'
            : t(isEdit ? 'assets.form.editTitle' : 'assets.form.createTitle')
        }
        description={
          isResubmit
            ? '根据退回意见修订资料；原拒绝记录永久保留，新提交会关联原申请并重新进入审批。'
            : isEdit
              ? '修改会校验资产版本和业务锁，并记录修改原因、字段快照与审计履历。'
              : '提交后生成入库申请，审批执行完成后才会写入正式资产台账。'
        }
      />
      <AssetFormEditor
        asset={asset}
        control={control}
        errors={errors}
        getValues={getValues}
        setValue={setValue}
        isEdit={isEdit}
        isResubmit={isResubmit}
        isSubmitting={mutation.isPending}
        options={options}
        showAmount={showAmount}
        submitFailed={submitFailed}
        onCancel={cancel}
        onSubmit={handleSubmit((values) => mutation.mutate(values))}
      />
    </div>,
  )
}
