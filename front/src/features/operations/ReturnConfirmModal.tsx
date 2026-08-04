import { useEffect } from 'react'
import { Form, Input, Modal, Radio, Select } from 'antd'
import type { ReturnCondition, ReturnInspectionItem } from '@/api/assetUsageReturn'
import type { OperationRequest } from '@/api/operations'

interface Option {
  label: string
  value: number
}

interface ReturnConfirmValues {
  return_location_id: number
  conditions: Record<string, ReturnCondition>
  descriptions?: Record<string, string>
}

interface ReturnConfirmModalProps {
  target: OperationRequest | null
  locations: Option[]
  loading: boolean
  onCancel: () => void
  onSubmit: (payload: { return_location_id: number; items: ReturnInspectionItem[] }) => void
}

export default function ReturnConfirmModal({
  target,
  locations,
  loading,
  onCancel,
  onSubmit,
}: ReturnConfirmModalProps) {
  const [form] = Form.useForm<ReturnConfirmValues>()
  const conditions = Form.useWatch('conditions', form) ?? {}

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
        <Form.Item
          name="return_location_id"
          label="退回闲置地点"
          rules={[{ required: true, message: '请选择退回地点' }]}
        >
          <Select showSearch optionFilterProp="label" options={locations} />
        </Form.Item>
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
        <p className="operations-modal-note">
          只有个人退库审批通过后才能验收。确认后资产由后端统一退回闲置；如发现损坏，系统会记录验收说明并按业务规则处理状态。
        </p>
      </Form>
    </Modal>
  )
}
