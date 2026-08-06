import type { FormEventHandler } from 'react'
import { useWatch } from 'react-hook-form'
import type { Control, FieldErrors } from 'react-hook-form'
import { Button } from 'antd'
import {
  Box,
  Building2,
  CircleDollarSign,
  Info,
  MessageSquareText,
  Save,
  ShieldCheck,
  X,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import SectionPanel from '@/components/ui/SectionPanel'
import { getAssetStatusMeta } from '@/features/assets/assetModel'
import type { AssetDetail } from '@/features/assets/types'
import {
  AmountFormField,
  DateFormField,
  ReadOnlyField,
  SelectFormField,
  TextAreaFormField,
  TextFormField,
} from './AssetFormFields'
import type { AssetFormInput } from './schema'

export interface AssetFormOptions {
  companies: Array<{ label: string; value: string }>
  categories: Array<{ label: string; value: string }>
  sources: Array<{ label: string; value: string }>
  units: Array<{ label: string; value: string }>
  suppliers: Array<{ label: string; value: string }>
  locations: Array<{ label: string; value: string }>
  managers: Array<{ label: string; value: string }>
}

interface SectionsProps {
  asset?: AssetDetail
  control: Control<AssetFormInput>
  errors: FieldErrors<AssetFormInput>
  isEdit: boolean
  isResubmit: boolean
  showAmount: boolean
  options: AssetFormOptions
}

function BasicSection({ asset, control, errors, isEdit, options }: SectionsProps) {
  const { t } = useTranslation()
  return (
    <SectionPanel
      title={t('assets.form.sections.basic')}
      icon={<Box aria-hidden="true" size={18} />}
    >
      {isEdit && asset ? (
        <div className="asset-form__readonly-grid">
          <ReadOnlyField label={t('assets.form.labels.asset_code')} value={asset.asset_code} />
          <ReadOnlyField
            label={t('assets.form.labels.status')}
            value={t(getAssetStatusMeta(asset.status).labelKey)}
          />
        </div>
      ) : (
        <div className="asset-form__generated-code" role="note">
          <Info aria-hidden="true" size={18} />
          <span>{t('assets.form.hints.generatedCode')}</span>
        </div>
      )}

      <div className="asset-form__field-grid">
        <TextFormField
          control={control}
          errors={errors}
          name="asset_name"
          label={t('assets.form.labels.asset_name')}
          placeholder={t('assets.form.placeholders.asset_name')}
          required
          wide
        />
        <SelectFormField
          control={control}
          errors={errors}
          name="category_name"
          label={t('assets.form.labels.category_name')}
          placeholder={t('assets.form.placeholders.category_name')}
          options={options.categories}
          required
        />
        <TextFormField
          control={control}
          errors={errors}
          name="model"
          label={t('assets.form.labels.model')}
          placeholder={t('assets.form.placeholders.model')}
        />
        <TextFormField
          control={control}
          errors={errors}
          name="serial_number"
          label={t('assets.form.labels.serial_number')}
          placeholder={t('assets.form.placeholders.serial_number')}
        />
        <TextFormField
          control={control}
          errors={errors}
          name="rfid_tag"
          label="RFID 标签"
          placeholder="可选，用于兼容既有 RFID 标识"
        />
      </div>
    </SectionPanel>
  )
}

function OwnershipSection({ asset, control, errors, isEdit, options }: SectionsProps) {
  const { t } = useTranslation()
  const emptyValue = t('assets.detail.unassigned')
  return (
    <SectionPanel
      title={t('assets.form.sections.ownership')}
      icon={<Building2 aria-hidden="true" size={18} />}
    >
      <div className="asset-form__field-grid">
        <SelectFormField
          control={control}
          errors={errors}
          name="company_name"
          label={t('assets.form.labels.company_name')}
          placeholder={t('assets.form.placeholders.company_name')}
          options={options.companies}
          disabled={isEdit}
          required
        />
        <SelectFormField
          control={control}
          errors={errors}
          name="location_name"
          label={t('assets.form.labels.location_name')}
          placeholder={t('assets.form.placeholders.location_name')}
          options={options.locations}
          required
        />
      </div>

      {isEdit && asset ? (
        <div className="asset-form__readonly-grid asset-form__readonly-grid--secondary">
          <ReadOnlyField
            label={t('assets.form.labels.user_name')}
            value={asset.user_name ?? emptyValue}
          />
          <ReadOnlyField
            label={t('assets.form.labels.department_name')}
            value={asset.department_name ?? emptyValue}
          />
        </div>
      ) : null}
    </SectionPanel>
  )
}

function PurchaseSection({ control, errors, showAmount, options }: SectionsProps) {
  const { t } = useTranslation()
  const purchaseAmount = useWatch({ control, name: 'purchase_amount' })
  return (
    <SectionPanel
      title={t('assets.form.sections.purchase')}
      icon={<CircleDollarSign aria-hidden="true" size={18} />}
    >
      <div className="asset-form__field-grid">
        <SelectFormField
          control={control}
          errors={errors}
          name="source_name"
          label={t('assets.form.labels.source_name')}
          placeholder={t('assets.form.placeholders.source_name')}
          options={options.sources}
          required
        />
        <SelectFormField
          control={control}
          errors={errors}
          name="supplier_name"
          label={t('assets.form.labels.supplier_name')}
          placeholder={t('assets.form.placeholders.supplier_name')}
          options={options.suppliers}
          allowClear
        />
        <DateFormField
          control={control}
          errors={errors}
          label={t('assets.form.labels.purchase_date')}
          placeholder={t('assets.form.placeholders.purchase_date')}
        />
        {showAmount ? (
          <AmountFormField
            control={control}
            errors={errors}
            label={t('assets.form.labels.purchase_amount')}
            placeholder={t('assets.form.placeholders.purchase_amount')}
          />
        ) : null}
        {showAmount && purchaseAmount === 0 ? (
          <TextFormField
            control={control}
            errors={errors}
            name="zero_amount_reason"
            label={t('assets.form.labels.zero_amount_reason')}
            placeholder={t('assets.form.placeholders.zero_amount_reason')}
            required
            wide
          />
        ) : null}
      </div>
    </SectionPanel>
  )
}

function ManagementSection({ control, errors, options }: SectionsProps) {
  const { t } = useTranslation()
  return (
    <SectionPanel
      title={t('assets.form.sections.management')}
      icon={<ShieldCheck aria-hidden="true" size={18} />}
    >
      <div className="asset-form__field-grid">
        <SelectFormField
          control={control}
          errors={errors}
          name="unit_name"
          label={t('assets.form.labels.unit_name')}
          placeholder={t('assets.form.placeholders.unit_name')}
          options={options.units}
          required
        />
        <SelectFormField
          control={control}
          errors={errors}
          name="manager_name"
          label={t('assets.form.labels.manager_name')}
          placeholder={t('assets.form.placeholders.manager_name')}
          options={options.managers}
          required
        />
      </div>
    </SectionPanel>
  )
}

function RemarkSection({ control, errors, isEdit, isResubmit }: SectionsProps) {
  const { t } = useTranslation()
  return (
    <SectionPanel
      title={t('assets.form.sections.remark')}
      icon={<MessageSquareText aria-hidden="true" size={18} />}
    >
      <div className="asset-form__field-grid">
        {isEdit || isResubmit ? (
          <TextAreaFormField
            control={control}
            errors={errors}
            name="change_reason"
            label={isResubmit ? '重新提交说明' : '修改原因'}
            placeholder={
              isResubmit
                ? '说明如何根据退回意见修改，本次提交会生成关联的新审批记录'
                : '说明本次资料调整原因，保存后写入审计记录'
            }
            required
          />
        ) : null}
        <TextAreaFormField
          control={control}
          errors={errors}
          label={t('assets.form.labels.remark')}
          placeholder={t('assets.form.placeholders.remark')}
        />
      </div>
    </SectionPanel>
  )
}

export interface AssetFormEditorProps extends SectionsProps {
  isSubmitting: boolean
  onCancel: () => void
  onSubmit: FormEventHandler<HTMLFormElement>
  submitFailed: boolean
}

export default function AssetFormEditor({
  asset,
  control,
  errors,
  isEdit,
  isResubmit,
  isSubmitting,
  onCancel,
  onSubmit,
  showAmount,
  options,
  submitFailed,
}: AssetFormEditorProps) {
  const { t } = useTranslation()
  const sections = { asset, control, errors, isEdit, isResubmit, showAmount, options }
  return (
    <>
      {isEdit && asset ? (
        <div className="asset-form__workflow-note" role="note">
          <Info aria-hidden="true" size={17} />
          <span>{t('assets.form.hints.workflowFields')}</span>
        </div>
      ) : null}
      {isResubmit ? (
        <div className="asset-form__workflow-note" role="note">
          <Info aria-hidden="true" size={17} />
          <span>原拒绝记录会永久保留，本次修改将生成关联的新一轮审批和新资产编码。</span>
        </div>
      ) : null}

      <form onSubmit={onSubmit} noValidate>
        <BasicSection {...sections} />
        <OwnershipSection {...sections} />
        <PurchaseSection {...sections} />
        <ManagementSection {...sections} />
        <RemarkSection {...sections} />

        {submitFailed ? (
          <div className="asset-form__submit-error" role="alert">
            {t('assets.form.errors.submit')}
          </div>
        ) : null}

        <div className="asset-form__actions">
          <Button type="default" icon={<X aria-hidden="true" size={16} />} onClick={onCancel}>
            {t('assets.form.actions.cancel')}
          </Button>
          <Button
            type="primary"
            htmlType="submit"
            icon={<Save aria-hidden="true" size={16} />}
            loading={isSubmitting}
          >
            {isResubmit
              ? '重新提交审批'
              : t(isEdit ? 'assets.form.actions.update' : 'assets.form.actions.create')}
          </Button>
        </div>
      </form>
    </>
  )
}
