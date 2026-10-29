import { useEffect, useMemo, useState } from 'react'
import dayjs from 'dayjs'
import { Alert, Button, DatePicker, Form, Input, InputNumber, Modal, Radio, Select } from 'antd'
import type { FormInstance } from 'antd'
import { Boxes, CircleCheckBig, PackageSearch, ScanLine, Send } from 'lucide-react'
import { lookupScanIntent } from '@/api/assets'
import BarcodeScanner from '@/components/scanner/BarcodeScanner'
import type { AssetUsageCandidate } from '@/api/assets'
import type { AssetScanIntent } from '@/features/assets/scan/scanIntentModel'
import {
  Building2,
  CalendarClock,
  CircleUserRound,
  PackageCheck,
  PackageMinus,
  ShieldAlert,
} from 'lucide-react'
import type {
  AssetUsageReturnAction,
  AssetUsageReturnSubmission,
  ReturnCondition,
} from '@/api/assetUsageReturn'
import type { PublicUsageObject } from '@/api/assetManagement'
import type { AssetSummary } from '@/features/assets/types'

interface Option {
  label: string
  value: number
  disabled?: boolean
}

interface CategoryOption extends Option {
  availableQuantity?: number
}

interface UsageReturnFormValues {
  action: AssetUsageReturnAction
  asset_ids?: number[]
  category_id?: number
  requested_quantity?: number
  target_user_id?: number
  public_object_id?: number
  location_id?: number
  return_company_id?: number
  return_usage_company_id?: number
  return_region_id?: number
  return_location_id?: number
  expected_return_at?: dayjs.Dayjs
  reason?: string
  conditions?: Record<string, ReturnCondition>
  descriptions?: Record<string, string>
}

interface UsageReturnModalProps {
  open: boolean
  assets: AssetSummary[]
  users: Option[]
  publicObjects: PublicUsageObject[]
  organizations: Option[]
  locationRegions: Option[]
  locationsByRegion: Record<number, Option[]>
  locations: Option[]
  categories: CategoryOption[]
  availableActions: AssetUsageReturnAction[]
  currentUserId?: number
  selfService?: boolean
  initialAction?: AssetUsageReturnAction
  initialAssetIds?: number[]
  scanOpen?: boolean
  onScanOpenChange?: (open: boolean) => void
  onAssetsChange?: (assets: AssetSummary[]) => void
  loading: boolean
  onCancel: () => void
  onSubmit: (submission: AssetUsageReturnSubmission) => void
}

type ActionOption = {
  value: AssetUsageReturnAction
  label: string
  description: string
  icon: typeof CircleUserRound
}

const EMPTY_ASSET_IDS: number[] = []

type UsageReturnPurpose = 'USE' | 'BORROW' | 'RETURN'

const purposeOptions: Array<{ value: UsageReturnPurpose; label: string }> = [
  { value: 'USE', label: '领用' },
  { value: 'BORROW', label: '借用' },
  { value: 'RETURN', label: '退库' },
]

const actionPurposeMap: Record<AssetUsageReturnAction, UsageReturnPurpose> = {
  PERSONAL_USE: 'USE',
  PUBLIC_USE: 'USE',
  PERSONAL_BORROW: 'BORROW',
  PUBLIC_BORROW: 'BORROW',
  PERSONAL_RETURN: 'RETURN',
  PUBLIC_RETURN: 'RETURN',
}

const actionOptions: ActionOption[] = [
  {
    value: 'PERSONAL_USE',
    label: '个人领用',
    description: '审批后由管理员发放，再由目标员工签收',
    icon: CircleUserRound,
  },
  {
    value: 'PUBLIC_USE',
    label: '公共领用',
    description: '投入会议室、直播间等公共对象',
    icon: Building2,
  },
  {
    value: 'PERSONAL_BORROW',
    label: '个人借用',
    description: '审批、发放、签收后开始借用',
    icon: CalendarClock,
  },
  {
    value: 'PUBLIC_BORROW',
    label: '公共借用',
    description: '公共对象临时借用，并跟踪预计归还时间',
    icon: CalendarClock,
  },
  {
    value: 'PERSONAL_RETURN',
    label: '个人退库',
    description: '退回本人当前领用的资产',
    icon: PackageMinus,
  },
  {
    value: 'PUBLIC_RETURN',
    label: '公共退库',
    description: '管理员验收公共资产并退回闲置',
    icon: PackageCheck,
  },
]

interface ActionCardGroupProps {
  options: ActionOption[]
  value?: AssetUsageReturnAction
  onChange?: (value: AssetUsageReturnAction) => void
}

function ActionCardGroup({ options, value, onChange }: ActionCardGroupProps) {
  return (
    <div className="usage-return-actions" role="radiogroup" aria-label="业务类型">
      {options.map(({ value: actionValue, label, description, icon: Icon }) => (
        <button
          key={actionValue}
          type="button"
          role="radio"
          aria-checked={value === actionValue}
          className={
            value === actionValue
              ? 'usage-return-action-card is-active'
              : 'usage-return-action-card'
          }
          onClick={() => {
            if (value !== actionValue) onChange?.(actionValue)
          }}
        >
          <Icon size={17} aria-hidden="true" />
          <span className="usage-return-action-card__content">
            <strong>{label}</strong>
            <small>{description}</small>
          </span>
        </button>
      ))}
    </div>
  )
}

const resetUsageFields = (form: FormInstance<UsageReturnFormValues>, keepAssetIds = false) => {
  form.setFieldsValue({
    asset_ids: keepAssetIds ? form.getFieldValue('asset_ids') : [],
    category_id: undefined,
    requested_quantity: undefined,
    target_user_id: undefined,
    public_object_id: undefined,
    location_id: undefined,
    return_company_id: undefined,
    return_usage_company_id: undefined,
    return_region_id: undefined,
    return_location_id: undefined,
    expected_return_at: undefined,
    reason: undefined,
    conditions: {},
    descriptions: {},
  })
}

function CategoryCardGroup({
  options,
  value,
  onChange,
  onValueChange,
}: {
  options: CategoryOption[]
  value?: number
  onChange?: (value: number) => void
  onValueChange?: (value: number) => void
}) {
  return (
    <div className="usage-return-category-grid" role="radiogroup" aria-label="资产类别">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          disabled={option.disabled}
          className={
            value === option.value
              ? 'usage-return-category-card is-active'
              : 'usage-return-category-card'
          }
          onClick={() => {
            if (value === option.value) return
            onChange?.(option.value)
            onValueChange?.(option.value)
          }}
        >
          <span className="usage-return-category-card__name">{option.label}</span>
          <strong className="usage-return-category-card__quantity">
            {option.disabled || !option.availableQuantity
              ? '暂无可领'
              : `可领 ${option.availableQuantity}`}
          </strong>
        </button>
      ))}
    </div>
  )
}

function allowedAsset(
  asset: AssetSummary,
  action: AssetUsageReturnAction,
  currentUserId?: number,
): boolean {
  if (
    action === 'PERSONAL_USE' ||
    action === 'PUBLIC_USE' ||
    action === 'PERSONAL_BORROW' ||
    action === 'PUBLIC_BORROW'
  )
    return asset.status === 'IDLE'
  if (action === 'PERSONAL_RETURN') {
    return (
      asset.status === 'IN_USE' &&
      asset.usage_type === 'PERSONAL' &&
      asset.holder_user_id === currentUserId
    )
  }
  return asset.status === 'IN_USE' && asset.usage_type === 'PUBLIC'
}

export default function UsageReturnModal({
  open,
  assets,
  users,
  publicObjects,
  organizations,
  locationRegions,
  locationsByRegion,
  locations,
  categories,
  availableActions,
  currentUserId,
  selfService = false,
  initialAction,
  initialAssetIds = EMPTY_ASSET_IDS,
  scanOpen = false,
  onScanOpenChange,
  onAssetsChange,
  loading,
  onCancel,
  onSubmit,
}: UsageReturnModalProps) {
  const [form] = Form.useForm<UsageReturnFormValues>()
  const [formValues, setFormValues] = useState<Partial<UsageReturnFormValues>>({})
  const [scannedAsset, setScannedAsset] = useState<AssetUsageCandidate | null>(null)
  const [scannedIntent, setScannedIntent] = useState<AssetScanIntent | null>(null)
  const [scanLoading, setScanLoading] = useState(false)

  const action = formValues.action
  const watchedCategoryId = formValues.category_id
  const watchedAssetIds = formValues.asset_ids
  const returnRegionId = formValues.return_region_id
  const conditions = formValues.conditions ?? {}
  const syncFormValues = () => setFormValues(form.getFieldsValue(true))

  const isSelfPersonalAction =
    selfService && (action === 'PERSONAL_USE' || action === 'PERSONAL_BORROW')
  const isEmployeeUseFlow = selfService && action === 'PERSONAL_USE' && !scannedAsset
  const isScannedAssetAction =
    action === 'PERSONAL_USE' ||
    action === 'PERSONAL_BORROW' ||
    action === 'PUBLIC_USE' ||
    action === 'PUBLIC_BORROW'
  const selectedAssets = useMemo(
    () => assets.filter((asset) => (watchedAssetIds ?? []).includes(asset.id)),
    [assets, watchedAssetIds],
  )
  const selectableAssets = useMemo(
    () => assets.filter((asset) => action && allowedAsset(asset, action, currentUserId)),
    [action, assets, currentUserId],
  )
  const selectedCategory = categories.find((category) => category.value === watchedCategoryId)
  const selectedCategoryQuantity = selectedCategory?.availableQuantity ?? 0
  const applyScannedAsset = async (value: string) => {
    setScanLoading(true)
    try {
      const normalized = value.trim()
      const intent = await lookupScanIntent({ asset_code: normalized })
      const scanned: AssetSummary = {
        id: intent.id,
        version: 1,
        asset_code: intent.asset_code,
        asset_name: intent.asset_name,
        category_name: intent.category_name,
        status: intent.status,
        organization_id: intent.organization_id,
        location_name: intent.location_name,
        company_name: intent.organization_name,
        source_name: '',
        unit_name: '',
        purchase_date: '',
        purchase_amount: 0,
        information_complete: true,
        usage_type: intent.usage_type ?? undefined,
        holder_user_id: intent.holder_user_id ?? undefined,
        public_object_id: intent.public_object_id ?? undefined,
      }
      const currentAction = form.getFieldValue('action') as AssetUsageReturnAction | undefined
      const currentActionAllowed =
        currentAction &&
        availableActions.includes(currentAction) &&
        (intent.scenarios as string[]).includes(currentAction)
      const nextAction = currentActionAllowed
        ? currentAction
        : intent.scenarios.find((scenario) => availableActions.includes(scenario))
      const candidate: AssetUsageCandidate = {
        id: intent.id,
        asset_code: intent.asset_code,
        asset_name: intent.asset_name,
        status: 'IDLE',
        category_id: intent.category_id,
        category_name: intent.category_name,
        organization_id: intent.organization_id,
        organization_name: intent.organization_name,
        location_id: intent.location_id ?? undefined,
        location_name: intent.location_name,
      }
      setScannedAsset(candidate)
      setScannedIntent(intent)
      form.setFieldsValue({
        action: nextAction ?? form.getFieldValue('action'),
        asset_ids: [intent.id],
        category_id: undefined,
        requested_quantity: undefined,
        location_id: intent.location_id ?? undefined,
      })
      setFormValues(form.getFieldsValue(true))
      onAssetsChange?.([scanned, ...assets.filter((item) => item.id !== scanned.id)])
      onScanOpenChange?.(false)
    } catch (error) {
      setScannedAsset(null)
      if (error instanceof Error) throw error
      throw new Error('扫码识别失败')
    } finally {
      setScanLoading(false)
    }
  }

  useEffect(() => {
    if (!open) {
      setScannedAsset(null)
      setScannedIntent(null)
      return
    }
    form.resetFields()
    form.setFieldsValue({
      action:
        initialAction && availableActions.includes(initialAction)
          ? initialAction
          : availableActions[0],
      ...(initialAssetIds.length ? { asset_ids: initialAssetIds } : {}),
      conditions: {},
      descriptions: {},
    })
    setFormValues(form.getFieldsValue(true))
  }, [availableActions, form, initialAction, initialAssetIds, open])

  const submit = async () => {
    const values = await form.validateFields()
    const asset_ids = values.asset_ids ?? []
    if (values.action === 'PERSONAL_USE') {
      onSubmit(
        selfService && scannedAsset
          ? {
              action: 'PERSONAL_USE',
              asset_ids: [scannedAsset.id],
              location_id: values.location_id,
              reason: values.reason?.trim() || undefined,
            }
          : selfService
            ? {
                action: 'PERSONAL_USE',
                category_id: values.category_id as number,
                requested_quantity: values.requested_quantity as number,
                location_id: values.location_id,
                reason: values.reason?.trim() || undefined,
              }
            : {
                action: 'PERSONAL_USE',
                asset_ids,
                target_user_id: values.target_user_id as number,
                location_id: values.location_id,
              },
      )
      return
    }
    if (values.action === 'PERSONAL_BORROW') {
      onSubmit(
        selfService
          ? scannedIntent
            ? {
                action: 'PERSONAL_BORROW',
                asset_ids: [scannedIntent.id],
                location_id: values.location_id,
                expected_return_at: values.expected_return_at?.toISOString() ?? '',
                reason: values.reason?.trim() || undefined,
              }
            : {
                action: 'PERSONAL_BORROW',
                category_id: values.category_id as number,
                requested_quantity: values.requested_quantity as number,
                location_id: values.location_id,
                expected_return_at: values.expected_return_at?.toISOString() ?? '',
                reason: values.reason?.trim() || undefined,
              }
          : {
              action: 'PERSONAL_BORROW',
              asset_ids,
              target_user_id: values.target_user_id as number,
              location_id: values.location_id,
              expected_return_at: values.expected_return_at?.toISOString() ?? '',
            },
      )
      return
    }
    if (values.action === 'PUBLIC_USE') {
      onSubmit({
        action: values.action,
        asset_ids,
        public_object_id: values.public_object_id as number,
        location_id: values.location_id as number,
      })
      return
    }
    if (values.action === 'PUBLIC_BORROW') {
      onSubmit({
        action: values.action,
        asset_ids,
        public_object_id: values.public_object_id as number,
        location_id: values.location_id as number,
        expected_return_at: values.expected_return_at?.toISOString() ?? '',
      })
      return
    }
    if (values.action === 'PERSONAL_RETURN') {
      onSubmit({ action: values.action, asset_ids })
      return
    }
    onSubmit({
      action: values.action,
      asset_ids,
      return_company_id: values.return_company_id as number,
      return_usage_company_id: values.return_usage_company_id as number,
      return_region_id: values.return_region_id as number,
      return_location_id: values.return_location_id as number,
      items: selectedAssets.map((asset) => ({
        asset_id: asset.id,
        condition: values.conditions?.[String(asset.id)] ?? 'NORMAL',
        condition_description: values.descriptions?.[String(asset.id)]?.trim() || undefined,
      })),
    })
  }

  const activeMeta = actionOptions.find((item) => item.value === action)
  const activePurpose = action ? actionPurposeMap[action] : 'USE'
  const purposeActionOptions = actionOptions.filter(
    (item) =>
      actionPurposeMap[item.value] === activePurpose && availableActions.includes(item.value),
  )
  return (
    <Modal
      open={open}
      width={760}
      title={isEmployeeUseFlow ? '我要领用' : '发起资产领用 / 退库'}
      className="operations-glass-modal usage-return-modal"
      okText={isEmployeeUseFlow ? '提交领用申请' : '提交真实申请'}
      cancelText="取消"
      confirmLoading={loading}
      onCancel={onCancel}
      onOk={() => void submit()}
    >
      {isEmployeeUseFlow ? (
        <div className="usage-return-employee-hero">
          <div>
            <span>员工自助</span>
            <strong>我要领用</strong>
            <small>选择资产类别和数量；审批通过后管理员发放，收到资产后签收。</small>
          </div>
          <PackageSearch size={38} aria-hidden="true" />
        </div>
      ) : (
        <>
          <Alert
            style={{ marginBottom: 16 }}
            type={scannedAsset ? 'success' : 'info'}
            showIcon
            icon={<ScanLine size={15} />}
            message={
              scannedAsset
                ? `已识别：${scannedAsset.asset_name} · ${scannedAsset.asset_code}`
                : '可打开手机摄像头扫描资产二维码或条形码，识别后自动预选该资产。'
            }
          />
          <Button
            block
            size="large"
            icon={<ScanLine size={16} />}
            onClick={() => onScanOpenChange?.(true)}
          >
            扫码添加领用资产
          </Button>
        </>
      )}
      <Form form={form} layout="vertical" requiredMark={false} onValuesChange={syncFormValues}>
        {isEmployeeUseFlow ? (
          <div className="usage-return-steps" aria-label="领用流程">
            {[
              { icon: Send, label: '提交申请' },
              { icon: CircleCheckBig, label: '审批' },
              { icon: Boxes, label: '管理员发放' },
              { icon: PackageCheck, label: '员工签收' },
            ].map(({ icon: Icon, label }, index, items) => (
              <div key={label} className="usage-return-step">
                <Icon size={15} aria-hidden="true" />
                <span>{label}</span>
                {index < items.length - 1 ? <i aria-hidden="true" /> : null}
              </div>
            ))}
          </div>
        ) : (
          <>
            <Form.Item label="业务目的">
              <Radio.Group
                value={activePurpose}
                optionType="button"
                buttonStyle="solid"
                block
                onChange={(event) => {
                  const purpose = event.target.value as UsageReturnPurpose
                  const nextAction = actionOptions.find(
                    (item) =>
                      actionPurposeMap[item.value] === purpose &&
                      availableActions.includes(item.value),
                  )?.value
                  if (nextAction) {
                    form.setFieldsValue({ action: nextAction })
                    resetUsageFields(form)
                    syncFormValues()
                  }
                }}
              >
                {purposeOptions.map((option) => (
                  <Radio.Button key={option.value} value={option.value}>
                    {option.label}
                  </Radio.Button>
                ))}
              </Radio.Group>
            </Form.Item>
            <Form.Item name="action" label="办理方式" rules={[{ required: true }]}>
              <ActionCardGroup
                options={purposeActionOptions}
                onChange={() => {
                  resetUsageFields(form)
                  syncFormValues()
                }}
              />
            </Form.Item>
            <div className="usage-return-context">
              {activeMeta ? (
                <activeMeta.icon size={18} aria-hidden="true" />
              ) : (
                <ShieldAlert size={18} />
              )}
              <div>
                <strong>{activeMeta?.label ?? '领用与退库'}</strong>
                <span>
                  {activeMeta?.description ?? '所有结果由后端校验并写入审批、履历和审计。'}
                </span>
              </div>
            </div>
          </>
        )}

        {isScannedAssetAction && scannedAsset ? (
          <Form.Item
            name="asset_ids"
            label="扫码识别资产"
            rules={[{ required: true, type: 'array', min: 1, message: '请先扫码识别资产' }]}
          >
            <Select
              mode="multiple"
              options={[
                {
                  value: scannedAsset.id,
                  label: `${scannedAsset.asset_name} · ${scannedAsset.asset_code}`,
                },
              ]}
            />
          </Form.Item>
        ) : null}

        {isSelfPersonalAction && !scannedAsset ? (
          <>
            {action === 'PERSONAL_USE' ? (
              <>
                <Form.Item
                  name="category_id"
                  label="选择资产类别"
                  rules={[{ required: true, message: '请选择资产类别' }]}
                >
                  <CategoryCardGroup
                    options={categories}
                    onValueChange={() => {
                      form.setFieldsValue({ requested_quantity: 1 })
                      syncFormValues()
                    }}
                  />
                </Form.Item>
                {selectedCategory &&
                selectedCategoryQuantity > 0 &&
                selectedCategoryQuantity <= 3 ? (
                  <Alert
                    className="usage-return-stock-alert"
                    type={selectedCategoryQuantity === 1 ? 'warning' : 'info'}
                    showIcon
                    message={
                      selectedCategoryQuantity === 1
                        ? '该类别仅剩 1 件，提交后需等待审批与发放。'
                        : `该类别仅剩 ${selectedCategoryQuantity} 件，最多可申请 ${selectedCategoryQuantity} 件。`
                    }
                  />
                ) : null}
                <div className="operations-form-grid">
                  <Form.Item
                    name="requested_quantity"
                    label="申请数量"
                    rules={[
                      { required: true, message: '请输入申请数量' },
                      {
                        validator: (_rule, value: number | undefined) => {
                          if (!selectedCategoryQuantity) return Promise.resolve()
                          if (!value || value < 1) return Promise.reject(new Error('至少申请 1 件'))
                          if (value > selectedCategoryQuantity)
                            return Promise.reject(
                              new Error(
                                `超过当前可领数量，最多可申请 ${selectedCategoryQuantity} 件`,
                              ),
                            )
                          return Promise.resolve()
                        },
                      },
                    ]}
                  >
                    <InputNumber
                      min={1}
                      max={selectedCategoryQuantity || 100}
                      precision={0}
                      style={{ width: '100%' }}
                      addonAfter="件"
                    />
                  </Form.Item>
                  <Form.Item label="申请人">
                    <Input value="当前登录员工（本人）" disabled />
                  </Form.Item>
                </div>
                <Form.Item name="location_id" label="期望使用地点">
                  <Select
                    allowClear
                    showSearch
                    optionFilterProp="label"
                    options={locations}
                    placeholder="可选，由管理员发放时确认"
                  />
                </Form.Item>
                <Form.Item name="reason" label="申请原因">
                  <Input.TextArea
                    rows={3}
                    maxLength={2000}
                    showCount
                    placeholder="说明用途、项目或使用场景，便于审批人判断"
                  />
                </Form.Item>
              </>
            ) : (
              <>
                <div className="operations-form-grid">
                  <Form.Item
                    name="category_id"
                    label="资产类别"
                    rules={[{ required: true, message: '请选择资产类别' }]}
                  >
                    <Select
                      showSearch
                      optionFilterProp="label"
                      options={categories}
                      placeholder="按类别申请，由管理员统一分配"
                    />
                  </Form.Item>
                  <Form.Item
                    name="requested_quantity"
                    label="申请数量"
                    rules={[{ required: true, message: '请输入申请数量' }]}
                  >
                    <InputNumber min={1} max={100} precision={0} style={{ width: '100%' }} />
                  </Form.Item>
                </div>
                <div className="operations-form-grid">
                  <Form.Item label="申请人">
                    <Input value="当前登录员工（本人）" disabled />
                  </Form.Item>
                  <Form.Item name="location_id" label="期望使用地点">
                    <Select
                      allowClear
                      showSearch
                      optionFilterProp="label"
                      options={locations}
                      placeholder="可选，由管理员发放时确认"
                    />
                  </Form.Item>
                </div>
                <Form.Item name="reason" label="申请原因">
                  <Input.TextArea
                    rows={3}
                    maxLength={2000}
                    showCount
                    placeholder="说明用途、项目或使用场景，便于审批人判断"
                  />
                </Form.Item>
              </>
            )}
          </>
        ) : (
          <Form.Item
            name="asset_ids"
            label="选择资产"
            rules={[{ required: true, type: 'array', min: 1, message: '请选择至少一件资产' }]}
          >
            <Select
              mode="multiple"
              showSearch
              optionFilterProp="label"
              maxTagCount="responsive"
              placeholder={
                selectableAssets.length ? '按名称或编码选择资产' : '当前没有可办理的资产'
              }
              options={selectableAssets.map((asset) => ({
                value: asset.id,
                label: `${asset.asset_name} · ${asset.asset_code}`,
              }))}
            />
          </Form.Item>
        )}

        {!isSelfPersonalAction && (action === 'PERSONAL_USE' || action === 'PERSONAL_BORROW') ? (
          <div className="operations-form-grid">
            <Form.Item
              name="target_user_id"
              label="领用员工"
              rules={[{ required: true, message: '请选择领用员工' }]}
            >
              <Select
                showSearch
                optionFilterProp="label"
                options={users}
                placeholder="选择在职员工"
              />
            </Form.Item>
            <Form.Item name="location_id" label="领用后地点">
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                options={locations}
                placeholder="不修改可留空"
              />
            </Form.Item>
          </div>
        ) : null}

        {action === 'PERSONAL_BORROW' || action === 'PUBLIC_BORROW' ? (
          <Form.Item
            name="expected_return_at"
            label="预计归还时间"
            rules={[{ required: true, message: '请选择预计归还时间' }]}
          >
            <DatePicker
              showTime
              disabledDate={(value) => value.isBefore(dayjs().startOf('day'))}
              style={{ width: '100%' }}
              placeholder="选择预计归还时间"
            />
          </Form.Item>
        ) : null}

        {action === 'PUBLIC_USE' || action === 'PUBLIC_BORROW' ? (
          <div className="operations-form-grid">
            <Form.Item
              name="public_object_id"
              label="公共使用对象"
              rules={[{ required: true, message: '请选择公共使用对象' }]}
            >
              <Select
                showSearch
                optionFilterProp="label"
                options={publicObjects
                  .filter((item) => item.status === 'ENABLED')
                  .map((item) => ({ value: item.id, label: `${item.name} · ${item.code}` }))}
                placeholder="会议室、直播间或其他公共对象"
              />
            </Form.Item>
            <Form.Item
              name="location_id"
              label="投入使用地点"
              rules={[{ required: true, message: '请选择地点' }]}
            >
              <Select showSearch optionFilterProp="label" options={locations} />
            </Form.Item>
          </div>
        ) : null}

        {action === 'PUBLIC_RETURN' ? (
          <>
            <div className="usage-return-destination-grid">
              <Form.Item
                name="return_company_id"
                label="退库后所属公司"
                rules={[{ required: true, message: '请选择退库后所属公司' }]}
              >
                <Select
                  showSearch
                  optionFilterProp="label"
                  options={organizations}
                  onChange={() => form.setFieldValue('return_region_id', undefined)}
                />
              </Form.Item>
              <Form.Item
                name="return_usage_company_id"
                label="退库后使用公司"
                rules={[{ required: true, message: '请选择退库后使用公司' }]}
              >
                <Select showSearch optionFilterProp="label" options={organizations} />
              </Form.Item>
              <Form.Item
                name="return_region_id"
                label="退库后区域"
                rules={[{ required: true, message: '请选择退库后区域' }]}
              >
                <Select
                  showSearch
                  optionFilterProp="label"
                  options={locationRegions}
                  onChange={() => form.setFieldValue('return_location_id', undefined)}
                />
              </Form.Item>
              <Form.Item
                name="return_location_id"
                label="退库后存放地点"
                rules={[{ required: true, message: '请选择退库后存放地点' }]}
              >
                <Select
                  showSearch
                  optionFilterProp="label"
                  options={(returnRegionId ? locationsByRegion[returnRegionId] : undefined) ?? []}
                  disabled={!returnRegionId}
                />
              </Form.Item>
            </div>
            {selectedAssets.length ? (
              <div className="usage-return-inspections">
                <div className="usage-return-inspections__heading">
                  <strong>逐件验收</strong>
                  <span>发现损坏时必须填写情况说明</span>
                </div>
                {selectedAssets.map((asset) => {
                  const key = String(asset.id)
                  return (
                    <article key={asset.id} className="usage-return-inspection">
                      <div>
                        <strong>{asset.asset_name}</strong>
                        <span>{asset.asset_code}</span>
                      </div>
                      <Form.Item
                        name={['conditions', key]}
                        initialValue="NORMAL"
                        rules={[{ required: true }]}
                      >
                        <Radio.Group optionType="button" buttonStyle="solid">
                          <Radio.Button value="NORMAL">外观正常</Radio.Button>
                          <Radio.Button value="DAMAGED">发现损坏</Radio.Button>
                        </Radio.Group>
                      </Form.Item>
                      {conditions[key] === 'DAMAGED' ? (
                        <Form.Item
                          name={['descriptions', key]}
                          rules={[{ required: true, min: 2, message: '请填写损坏情况' }]}
                        >
                          <Input.TextArea
                            rows={2}
                            maxLength={500}
                            showCount
                            placeholder="描述损坏位置、现象和配件缺失情况"
                          />
                        </Form.Item>
                      ) : null}
                    </article>
                  )
                })}
              </div>
            ) : null}
          </>
        ) : null}

        <p className="operations-modal-note">
          {isEmployeeUseFlow
            ? '提交后可在“我发起的申请”查看审批进度；审批通过后管理员发放具体资产，收到资产后需要签收确认。'
            : selfService
              ? '员工可按资产类别和数量提交领用或借用申请，并在流程列表查看审批进度；审批通过后由系统分配当前空闲资产。个人退库仍需选择本人名下资产。'
              : '“代员工申请”必须经过审批、管理员发放和员工签收。管理员如需立即调整资产状态或使用人，请在资产台账中选中单件资产后使用“直接维护”。'}
        </p>
      </Form>
      <BarcodeScanner
        open={scanOpen}
        title="扫码识别资产"
        onClose={() => onScanOpenChange?.(false)}
        loading={scanLoading}
        scanToUse
        onDetected={(value) => {
          void applyScannedAsset(value)
        }}
      />
    </Modal>
  )
}
