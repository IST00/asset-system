import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'
import { Modal, message } from 'antd'
import { createAsset, getAsset, updateAsset } from '@/api/assets'
import PageHeader from '@/components/ui/PageHeader'
import StatePanel from '@/components/ui/StatePanel'
import { canCreateAsset } from '@/features/assets/assetModel'
import { useAuthStore } from '@/store/auth'
import AssetFormLoading from './AssetFormLoading'
import AssetFormEditor from './AssetFormSections'
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

export default function AssetForm() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const permissions = useAuthStore((state) => state.user?.permissions)
  const [messageApi, messageContextHolder] = message.useMessage()
  const [modalApi, modalContextHolder] = Modal.useModal()
  const { assetId } = useParams<{ assetId: string }>()
  const mode = getAssetFormMode(assetId)
  const editAssetId = mode?.mode === 'edit' ? mode.assetId : null
  const showAmount = mode ? canShowAssetAmount(mode.mode, permissions) : false
  const [submitFailed, setSubmitFailed] = useState(false)
  const {
    control,
    handleSubmit,
    reset,
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

  useEffect(() => {
    if (assetQuery.data) reset(toAssetFormValues(assetQuery.data))
  }, [assetQuery.data, reset])

  const mutation = useMutation({
    mutationFn: (values: AssetFormInput) => {
      if (mode?.mode === 'edit') {
        if (!showAmount) {
          const originalAsset = assetQuery.data
          if (!originalAsset) return Promise.reject(new Error('ASSET_NOT_LOADED'))
          return updateAsset(
            mode.assetId,
            buildAssetFormPayload(values, {
              purchase_amount: originalAsset.purchase_amount,
              zero_amount_reason: originalAsset.zero_amount_reason,
            }),
          )
        }
        return updateAsset(mode.assetId, buildAssetFormPayload(values))
      }
      if (mode?.mode === 'create') return createAsset(buildAssetFormPayload(values))
      return Promise.reject(new Error('INVALID_ASSET_ID'))
    },
    onMutate: () => setSubmitFailed(false),
    onSuccess: async (asset) => {
      queryClient.setQueryData(getAssetDetailQueryKey(asset.id), asset)
      void queryClient.invalidateQueries({ queryKey: getAssetListQueryKey() })
      await messageApi.success({
        content: t(
          mode?.mode === 'edit' ? 'assets.form.updateSuccess' : 'assets.form.createSuccess',
        ),
        duration: 0.35,
      })
      navigate(`/assets/${asset.id}`)
    },
    onError: () => setSubmitFailed(true),
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

  if (mode === null) {
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

  if (mode.mode === 'edit' && assetQuery.isLoading) {
    return renderWithContext(
      <div className="asset-form" aria-label={t('assets.form.loading')} aria-busy="true">
        <PageHeader
          title={t('assets.form.editTitle')}
          description={t('assets.form.editDescription')}
        />
        <AssetFormLoading />
      </div>,
    )
  }

  if (mode.mode === 'edit' && assetQuery.isError) {
    const notFound =
      assetQuery.error instanceof Error && assetQuery.error.message === 'ASSET_NOT_FOUND'
    return renderWithContext(
      <div className="asset-form">
        <StatePanel
          mode={notFound ? 'empty' : 'error'}
          message={t(notFound ? 'assets.detail.notFound' : 'assets.form.errors.load')}
          retryLabel={notFound ? undefined : t('assets.form.actions.retry')}
          onRetry={notFound ? undefined : () => void assetQuery.refetch()}
        />
      </div>,
    )
  }

  const asset = assetQuery.data
  const isEdit = mode.mode === 'edit'
  return renderWithContext(
    <div className="asset-form">
      <PageHeader
        title={t(isEdit ? 'assets.form.editTitle' : 'assets.form.createTitle')}
        description={t(isEdit ? 'assets.form.editDescription' : 'assets.form.createDescription')}
      />
      <AssetFormEditor
        asset={asset}
        control={control}
        errors={errors}
        isEdit={isEdit}
        isSubmitting={mutation.isPending}
        showAmount={showAmount}
        submitFailed={submitFailed}
        onCancel={cancel}
        onSubmit={handleSubmit((values) => mutation.mutate(values))}
      />
    </div>,
  )
}
