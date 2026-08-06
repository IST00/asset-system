import { useEffect, useMemo } from 'react'
import { Form, Input, Modal, Radio, Select } from 'antd'
import { Building2, CircleUserRound, PackageCheck, PackageMinus, ShieldAlert } from 'lucide-react'
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
}

interface UsageReturnFormValues {
  action: AssetUsageReturnAction
  asset_ids: number[]
  target_user_id?: number
  public_object_id?: number
  location_id?: number
  return_location_id?: number
  conditions?: Record<string, ReturnCondition>
  descriptions?: Record<string, string>
}

interface UsageReturnModalProps {
  open: boolean
  assets: AssetSummary[]
  users: Option[]
  publicObjects: PublicUsageObject[]
  locations: Option[]
  availableActions: AssetUsageReturnAction[]
  currentUserId?: number
  loading: boolean
  onCancel: () => void
  onSubmit: (submission: AssetUsageReturnSubmission) => void
}

const actionOptions: Array<{
  value: AssetUsageReturnAction
  label: string
  description: string
  icon: typeof CircleUserRound
}> = [
  {
    value: 'PERSONAL_USE',
    label: '个人领用',
    description: '管理员指定员工，员工确认后生效',
    icon: CircleUserRound,
  },
  {
    value: 'PUBLIC_USE',
    label: '公共领用',
    description: '投入会议室、直播间等公共对象',
    icon: Building2,
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

function allowedAsset(
  asset: AssetSummary,
  action: AssetUsageReturnAction,
  currentUserId?: number,
): boolean {
  if (action === 'PERSONAL_USE' || action === 'PUBLIC_USE') return asset.status === 'IDLE'
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
  locations,
  availableActions,
  currentUserId,
  loading,
  onCancel,
  onSubmit,
}: UsageReturnModalProps) {
  const [form] = Form.useForm<UsageReturnFormValues>()
  const action = Form.useWatch('action', form)
  const watchedAssetIds = Form.useWatch('asset_ids', form)
  const conditions = Form.useWatch('conditions', form) ?? {}
  const selectedAssets = useMemo(
    () => assets.filter((asset) => (watchedAssetIds ?? []).includes(asset.id)),
    [assets, watchedAssetIds],
  )
  const selectableAssets = useMemo(
    () => assets.filter((asset) => action && allowedAsset(asset, action, currentUserId)),
    [action, assets, currentUserId],
  )

  useEffect(() => {
    if (!open) return
    form.resetFields()
    form.setFieldsValue({
      action: availableActions[0],
      asset_ids: [],
      conditions: {},
      descriptions: {},
    })
  }, [availableActions, form, open])

  const submit = async () => {
    const values = await form.validateFields()
    const asset_ids = values.asset_ids
    if (values.action === 'PERSONAL_USE') {
      onSubmit({
        action: values.action,
        asset_ids,
        target_user_id: values.target_user_id as number,
        location_id: values.location_id,
      })
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
    if (values.action === 'PERSONAL_RETURN') {
      onSubmit({ action: values.action, asset_ids })
      return
    }
    onSubmit({
      action: values.action,
      asset_ids,
      return_location_id: values.return_location_id as number,
      items: selectedAssets.map((asset) => ({
        asset_id: asset.id,
        condition: values.conditions?.[String(asset.id)] ?? 'NORMAL',
        condition_description: values.descriptions?.[String(asset.id)]?.trim() || undefined,
      })),
    })
  }

  const activeMeta = actionOptions.find((item) => item.value === action)

  return (
    <Modal
      open={open}
      width={760}
      title="发起资产领用 / 退库"
      className="operations-glass-modal usage-return-modal"
      okText="提交真实申请"
      cancelText="取消"
      confirmLoading={loading}
      onCancel={onCancel}
      onOk={() => void submit()}
    >
      <Form form={form} layout="vertical" requiredMark={false}>
        <Form.Item name="action" label="业务类型" rules={[{ required: true }]}>
          <Radio.Group
            className="usage-return-actions"
            onChange={() =>
              form.setFieldsValue({ asset_ids: [], conditions: {}, descriptions: {} })
            }
          >
            {actionOptions
              .filter((item) => availableActions.includes(item.value))
              .map(({ value, label, description, icon: Icon }) => (
                <Radio.Button key={value} value={value}>
                  <Icon size={17} aria-hidden="true" />
                  <span>
                    <strong>{label}</strong>
                    <small>{description}</small>
                  </span>
                </Radio.Button>
              ))}
          </Radio.Group>
        </Form.Item>

        <div className="usage-return-context">
          {activeMeta ? (
            <activeMeta.icon size={18} aria-hidden="true" />
          ) : (
            <ShieldAlert size={18} />
          )}
          <div>
            <strong>{activeMeta?.label ?? '领用与退库'}</strong>
            <span>{activeMeta?.description ?? '所有结果由后端校验并写入审批、履历和审计。'}</span>
          </div>
        </div>

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
            placeholder={selectableAssets.length ? '按名称或编码选择资产' : '当前没有可办理的资产'}
            options={selectableAssets.map((asset) => ({
              value: asset.id,
              label: `${asset.asset_name} · ${asset.asset_code}`,
            }))}
          />
        </Form.Item>

        {action === 'PERSONAL_USE' ? (
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

        {action === 'PUBLIC_USE' ? (
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
            <Form.Item
              name="return_location_id"
              label="退回闲置地点"
              rules={[{ required: true, message: '请选择退回地点' }]}
            >
              <Select showSearch optionFilterProp="label" options={locations} />
            </Form.Item>
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
          个人领用与个人退库会进入审批；公共领用和公共退库由有权限的管理员直接办理。系统会再次校验资产状态、数据范围和重复提交，不使用演示数据。
        </p>
      </Form>
    </Modal>
  )
}
