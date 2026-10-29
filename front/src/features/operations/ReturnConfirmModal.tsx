import { useEffect } from 'react'
import { Form, Input, Modal, Radio, Select } from 'antd'
import type { ReturnCondition, ReturnInspectionItem } from '@/api/assetUsageReturn'
import type { OperationRequest } from '@/api/operations'
import WorkflowEvidenceUpload from './WorkflowEvidenceUpload'

interface Option {
  label: string
  value: number
}

interface ReturnConfirmValues {
  return_company_id: number
  return_usage_company_id: number
  return_region_id: number
  return_location_id: number
  conditions: Record<string, ReturnCondition>
  descriptions?: Record<string, string>
}

interface ReturnConfirmModalProps {
  target: OperationRequest | null
  organizations: Option[]
  locationRegions: Option[]
  locationsByRegion: Record<number, Option[]>
  loading: boolean
  onCancel: () => void
  onSubmit: (payload: {
    return_company_id: number
    return_usage_company_id: number
    return_region_id: number
    return_location_id: number
    items: ReturnInspectionItem[]
  }) => void
}

export default function ReturnConfirmModal({
  target,
  organizations,
  locationRegions,
  locationsByRegion,
  loading,
  onCancel,
  onSubmit,
}: ReturnConfirmModalProps) {
  const [form] = Form.useForm<ReturnConfirmValues>()
  const conditions = Form.useWatch('conditions', form) ?? {}
  const selectedRegionId = Form.useWatch('return_region_id', form)

  useEffect(() => {
    if (!target) return
    form.resetFields()
    form.setFieldsValue({
      conditions: Object.fromEntries(
        target.assets.map((asset) => [String(asset.asset_id), 'NORMAL']),
      ),
    })
  }, [form, target])

  const submit = async () => {
    if (!target) return
    const values = await form.validateFields()
    onSubmit({
      return_company_id: values.return_company_id,
      return_usage_company_id: values.return_usage_company_id,
      return_region_id: values.return_region_id,
      return_location_id: values.return_location_id,
      items: target.assets.map((asset) => {
        const key = String(asset.asset_id)
        return {
          asset_id: asset.asset_id,
          condition: values.conditions[key] ?? 'NORMAL',
          condition_description: values.descriptions?.[key]?.trim() || undefined,
        }
      }),
    })
  }

  return (
    <Modal
      open={target !== null}
      width={680}
      title={`个人退库验收 · ${target?.request_no ?? ''}`}
      className="operations-glass-modal usage-return-modal"
      okText="确认验收并退库"
      cancelText="取消"
      confirmLoading={loading}
      onCancel={onCancel}
      onOk={() => void submit()}
    >
      <Form form={form} layout="vertical" requiredMark={false}>
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
              options={locationsByRegion[selectedRegionId] ?? []}
              disabled={!selectedRegionId}
            />
          </Form.Item>
        </div>
        <div className="usage-return-inspections">
          <div className="usage-return-inspections__heading">
            <strong>逐件验收</strong>
            <span>损坏资产会保留状态说明并写入履历</span>
          </div>
          {(target?.assets ?? []).map((asset) => {
            const key = String(asset.asset_id)
            return (
              <article key={asset.asset_id} className="usage-return-inspection">
                <div>
                  <strong>{asset.asset_name}</strong>
                  <span>{asset.asset_code}</span>
                </div>
                <Form.Item name={['conditions', key]} rules={[{ required: true }]}>
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
        {target ? (
          <WorkflowEvidenceUpload
            businessId={target.id}
            businessType="RETURN_INSPECTION"
            documentType="INSPECTION_PHOTO"
            assets={target.assets}
            label="验收证据（可选）"
          />
        ) : null}
        <p className="operations-modal-note">
          只有个人退库审批通过后才能验收。确认后资产由后端统一退回闲置；如发现损坏，系统会记录验收说明并按业务规则处理状态。验收照片会绑定到对应资产和退库申请，便于后续追溯。
        </p>
      </Form>
    </Modal>
  )
}
