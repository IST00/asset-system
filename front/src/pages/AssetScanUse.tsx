import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, DatePicker, Form, Input, Radio, Select, Spin, Tag } from 'antd'
import { ScanLine } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import dayjs from 'dayjs'
import { assetUsageReturnApi, type AssetUsageReturnSubmission } from '@/api/assetUsageReturn'
import { masterDataApi, type TreeItem } from '@/api/administration'
import { getAsset, lookupScanIntent } from '@/api/assets'
import { assetManagementApi } from '@/api/assetManagement'
import { useAuthStore } from '@/store/auth'
import { OperationsHero } from '@/features/operations/OperationsUI'
import { isTransferHandoverPayload, parseScannedAssetValue } from '@/features/assets/scan/payload'
import { assetStatusLabel } from '@/utils/displayLabels'
import {
  assetScanActionMeta,
  assetScanActionOptions,
  selectScanAction,
  type AssetScanAction,
  type AssetScanIntent,
  type AssetScanPurpose,
} from '@/features/assets/scan/scanIntentModel'

interface FormValues {
  action?: AssetScanAction
  condition?: 'NORMAL' | 'DAMAGED'
  location_id?: number
  return_company_id?: number
  return_usage_company_id?: number
  return_region_id?: number
  return_location_id?: number
  target_user_id?: number
  reason?: string
  public_object_id?: number
  expected_return_at?: dayjs.Dayjs
}

const initialCondition = { NORMAL: 'NORMAL', DAMAGED: '发现损坏' } as const

const flattenTree = (items: TreeItem[]): TreeItem[] =>
  items.flatMap((item) => [item, ...flattenTree(item.children ?? [])])

export default function AssetScanUse() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const token = useAuthStore((state) => state.token)
  const user = useAuthStore((state) => state.user)
  const [form] = Form.useForm<FormValues>()
  const action = Form.useWatch('action', form)
  const condition = Form.useWatch('condition', form)
  const returnRegionId = Form.useWatch('return_region_id', form)

  const scanned = useMemo(
    () => parseScannedAssetValue(`${window.location.pathname}${window.location.search}`),
    [],
  )

  const isTransferHandover = isTransferHandoverPayload(scanned ?? ({} as never))
  const handoverToken = scanned?.handoverToken
  const intentQuery = useQuery({
    queryKey: ['asset-scan-use', 'intent', scanned?.assetCode],
    queryFn: () => {
      if (!scanned?.assetCode) throw new Error('缺少资产编码')
      return lookupScanIntent({ asset_code: scanned.assetCode })
    },
    enabled: Boolean(token && scanned?.assetCode),
    retry: false,
  })

  const handoverQuery = useQuery({
    queryKey: ['asset-transfer-handover', handoverToken],
    queryFn: () => {
      if (!handoverToken) throw new Error('缺少交接二维码标识')
      return assetManagementApi.transferHandoverByToken(handoverToken)
    },
    enabled: Boolean(token && handoverToken),
    retry: false,
  })

  const [handoverRemark, setHandoverRemark] = useState('')
  const claimHandoverMutation = useMutation({
    mutationFn: () => {
      if (!handoverToken) throw new Error('缺少交接二维码标识')
      return assetManagementApi.claimTransferHandoverByToken({
        handover_token: handoverToken,
        remark: handoverRemark.trim() || undefined,
      })
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['assets'] }),
        queryClient.invalidateQueries({ queryKey: ['asset-transfer-handover'] }),
        queryClient.invalidateQueries({ queryKey: ['transfer-handovers'] }),
        queryClient.invalidateQueries({ queryKey: ['asset-usage', 'my-assets'] }),
      ])
      navigate('/assets', { state: { transferHandoverCompleted: true } })
    },
  })

  const preferredPurpose = useMemo<AssetScanPurpose | undefined>(() => {
    const value = searchParams.get('preferred')
    return value === 'USE' || value === 'BORROW' || value === 'RETURN' || value === 'INVENTORY'
      ? value
      : undefined
  }, [searchParams])

  const detailQuery = useQuery({
    queryKey: ['asset-scan-use', 'detail', intentQuery.data?.id],
    queryFn: () => {
      const assetId = intentQuery.data?.id
      if (!assetId) throw new Error('缺少资产 ID')
      return getAsset(assetId)
    },
    enabled: Boolean(intentQuery.data?.id),
  })

  const referenceQuery = useQuery({
    queryKey: ['asset-usage', 'self-service-references'],
    queryFn: () => assetUsageReturnApi.selfServiceReferences(),
    enabled: Boolean(token),
  })

  const publicObjectQuery = useQuery({
    queryKey: ['public-usage-objects', 'scan-enabled'],
    queryFn: () => assetManagementApi.publicObjects(false),
    enabled: Boolean(token),
    staleTime: 60_000,
  })

  const publicObjectOptions = useMemo(
    () =>
      publicObjectQuery.data
        ?.filter((item) => item.status === 'ENABLED')
        .map((item) => ({ value: item.id, label: `${item.name} · ${item.code}` })) ?? [],
    [publicObjectQuery.data],
  )

  const actionOptions = useMemo(
    () => (intentQuery.data ? assetScanActionOptions(intentQuery.data) : []),
    [intentQuery.data],
  )

  const submitMutation = useMutation({
    mutationFn: async (values: FormValues) => {
      const intent = intentQuery.data
      if (!intent) throw new Error('请先扫码识别资产')
      if (values.action === 'PERSONAL_USE') {
        const submission: AssetUsageReturnSubmission = {
          action: 'PERSONAL_USE',
          asset_ids: [intent.id],
          location_id: values.location_id,
          reason: values.reason?.trim() || undefined,
        }
        return assetUsageReturnApi.submit(submission)
      }
      if (values.action === 'PERSONAL_BORROW') {
        const submission: AssetUsageReturnSubmission = {
          action: 'PERSONAL_BORROW',
          asset_ids: [intent.id],
          location_id: values.location_id,
          expected_return_at: values.expected_return_at?.toISOString() ?? '',
          reason: values.reason?.trim() || undefined,
        }
        return assetUsageReturnApi.submit(submission)
      }
      if (values.action === 'PUBLIC_USE') {
        const submission: AssetUsageReturnSubmission = {
          action: 'PUBLIC_USE',
          asset_ids: [intent.id],
          public_object_id: values.public_object_id ?? intent.public_object_id ?? 0,
          location_id: values.location_id ?? intent.location_id ?? 0,
        }
        return assetUsageReturnApi.submit(submission)
      }
      if (values.action === 'PUBLIC_BORROW') {
        const submission: AssetUsageReturnSubmission = {
          action: 'PUBLIC_BORROW',
          asset_ids: [intent.id],
          public_object_id: values.public_object_id ?? intent.public_object_id ?? 0,
          location_id: values.location_id ?? intent.location_id ?? 0,
          expected_return_at: values.expected_return_at?.toISOString() ?? '',
        }
        return assetUsageReturnApi.submit(submission)
      }
      if (values.action === 'PERSONAL_RETURN') {
        const submission: AssetUsageReturnSubmission = {
          action: 'PERSONAL_RETURN',
          asset_ids: [intent.id],
        }
        return assetUsageReturnApi.submit(submission)
      }
      if (values.action === 'PUBLIC_RETURN') {
        const submission: AssetUsageReturnSubmission = {
          action: 'PUBLIC_RETURN',
          asset_ids: [intent.id],
          return_company_id: values.return_company_id as number,
          return_usage_company_id: values.return_usage_company_id as number,
          return_region_id: values.return_region_id as number,
          return_location_id: values.return_location_id as number,
          items: [
            {
              asset_id: intent.id,
              condition: condition === 'DAMAGED' ? 'DAMAGED' : 'NORMAL',
              condition_description: values.reason?.trim() || undefined,
            },
          ],
        }
        return assetUsageReturnApi.submit(submission)
      }
      throw new Error('请选择扫码办理场景')
    },
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['operation-requests'] }),
        queryClient.invalidateQueries({ queryKey: ['assets'] }),
        queryClient.invalidateQueries({ queryKey: ['asset-usage', 'my-assets'] }),
        queryClient.invalidateQueries({ queryKey: ['workbench'] }),
      ])
      navigate('/workflows', { state: { scanUseRequestNo: result.request_no } })
    },
  })

  useEffect(() => {
    if (!intentQuery.data) return
    const preferredAction = form.getFieldValue('action') as AssetScanAction | undefined
    const nextAction = selectScanAction(intentQuery.data, preferredAction, preferredPurpose)
    form.setFieldsValue({
      action: nextAction,
      location_id: intentQuery.data.location_id ?? undefined,
      target_user_id: undefined,
      condition: 'NORMAL',
    })
  }, [form, intentQuery.data, preferredPurpose])

  const masterDataQuery = useQuery({
    queryKey: ['asset-scan-use', 'master-data'],
    queryFn: async () => {
      const [organizations, locations] = await Promise.all([
        masterDataApi.organizations(),
        masterDataApi.locations(),
      ])
      return { organizations, locations }
    },
    enabled: Boolean(token),
    staleTime: 60_000,
  })

  const organizationOptions = useMemo(
    () =>
      flattenTree(masterDataQuery.data?.organizations ?? [])
        .filter((item) => item.status !== 'DISABLED')
        .map((item) => ({ label: item.name, value: item.id })),
    [masterDataQuery.data?.organizations],
  )

  const locationRegions = useMemo(
    () =>
      flattenTree(masterDataQuery.data?.locations ?? [])
        .filter(
          (item) =>
            item.status !== 'DISABLED' &&
            (item.parent_id === undefined ||
              item.parent_id === null ||
              item.is_selectable === false),
        )
        .map((item) => ({ label: item.name, value: item.id })),
    [masterDataQuery.data?.locations],
  )

  const locationsByRegion = useMemo(() => {
    const mapping: Record<number, Array<{ label: string; value: number }>> = {}
    flattenTree(masterDataQuery.data?.locations ?? [])
      .filter((item) => item.status !== 'DISABLED' && item.is_selectable !== false)
      .forEach((item) => {
        const regionId = item.parent_id ?? item.id
        mapping[regionId] = [...(mapping[regionId] ?? []), { label: item.name, value: item.id }]
      })
    return mapping
  }, [masterDataQuery.data?.locations])

  const locationOptions = useMemo(
    () =>
      referenceQuery.data?.locations.map((location) => ({
        label: location.name,
        value: location.id,
      })) ?? [],
    [referenceQuery.data],
  )

  if (!token) return <Spin />

  if (isTransferHandover) {
    return (
      <div className="operations-page">
        <OperationsHero
          eyebrow="ASSET TRANSFER"
          title="扫码确认交接"
          description="确认后，所选资产的使用人将变更为当前登录账号。"
          icon={ScanLine}
          tone="cyan"
        />
        <Card style={{ marginTop: 24 }}>
          {handoverQuery.isLoading ? <Spin /> : null}
          {handoverQuery.isError ? (
            <Alert
              type="error"
              showIcon
              message={
                handoverQuery.error instanceof Error
                  ? handoverQuery.error.message
                  : '交接二维码无效或已被处理'
              }
            />
          ) : null}
          {handoverQuery.data ? (
            <>
              <div className="operations-table__primary">
                <strong>{handoverQuery.data.handover_no}</strong>
                <span>{handoverQuery.data.items.length} 件资产待接收</span>
              </div>
              <ul style={{ margin: '16px 0', paddingLeft: 20 }}>
                {handoverQuery.data.items.map((item) => (
                  <li key={item.asset_id}>
                    {item.asset_name} · {item.asset_code}
                  </li>
                ))}
              </ul>
              <Input.TextArea
                value={handoverRemark}
                onChange={(event) => setHandoverRemark(event.target.value)}
                placeholder="确认备注（可选）"
                maxLength={200}
                rows={3}
                style={{ marginBottom: 16 }}
              />
              <Button
                type="primary"
                size="large"
                block
                loading={claimHandoverMutation.isPending}
                onClick={() => claimHandoverMutation.mutate()}
              >
                确认接收并完成交接
              </Button>
              {claimHandoverMutation.isError ? (
                <Alert
                  style={{ marginTop: 16 }}
                  type="error"
                  showIcon
                  message={
                    claimHandoverMutation.error instanceof Error
                      ? claimHandoverMutation.error.message
                      : '交接确认失败'
                  }
                />
              ) : null}
            </>
          ) : null}
        </Card>
      </div>
    )
  }

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow="SCAN TO ACT"
        title="扫码办理"
        description="根据资产状态自动识别领用、借用、退库或盘点场景。"
        icon={ScanLine}
        tone="cyan"
      />

      {intentQuery.isLoading ? <Card loading style={{ marginTop: 24 }} /> : null}

      {!scanned || intentQuery.isError ? (
        <Alert
          style={{ marginTop: 24 }}
          type="error"
          showIcon
          message={
            !scanned
              ? '二维码内容无效，缺少资产编码'
              : intentQuery.error instanceof Error
                ? intentQuery.error.message
                : '扫码识别失败'
          }
        />
      ) : null}

      {intentQuery.data ? (
        <ScanUseForm intent={intentQuery.data} publicObjectOptions={publicObjectOptions} />
      ) : null}

      {detailQuery.data ? (
        <Alert
          style={{ marginTop: 16 }}
          type="success"
          showIcon
          message={`已加载资产详情：${detailQuery.data.asset_code}`}
        />
      ) : null}
    </div>
  )

  function ScanUseForm({
    intent,
    publicObjectOptions,
  }: {
    intent: AssetScanIntent
    publicObjectOptions: Array<{ value: number; label: string }>
  }) {
    const requiresReturnTime = action === 'PERSONAL_BORROW' || action === 'PUBLIC_BORROW'
    const isPublicWorkflow = action === 'PUBLIC_USE' || action === 'PUBLIC_BORROW'
    const isReturnInspection = action === 'PUBLIC_RETURN'
    const showReason =
      action === 'PERSONAL_USE' || action === 'PERSONAL_BORROW' || isReturnInspection
    const selectedAction = action ? assetScanActionMeta(action) : undefined

    return (
      <Card style={{ marginTop: 24 }}>
        <div className="operations-table__primary">
          <strong>{intent.asset_name}</strong>
          <span>{intent.asset_code}</span>
        </div>
        <div className="operations-grid operations-grid--three" style={{ marginTop: 16 }}>
          <span>分类：{intent.category_name}</span>
          <span>
            状态：
            <Tag color={intent.status === 'IN_USE' ? 'processing' : 'success'}>
              {assetStatusLabel(intent.status)}
            </Tag>
          </span>
          <span>公司：{intent.organization_name}</span>
          <span>地点：{intent.location_name}</span>
          {intent.public_object_name ? <span>公共对象：{intent.public_object_name}</span> : null}
          <span>申请人：{user?.nickname || user?.username || '当前登录人'}</span>
        </div>

        <Form form={form} layout="vertical" style={{ marginTop: 24 }}>
          <Form.Item name="action" label="办理场景" rules={[{ required: true }]}>
            <Radio.Group optionType="button" buttonStyle="solid" block>
              {actionOptions.map((option) => (
                <Radio.Button key={option.value} value={option.value}>
                  {option.label}
                </Radio.Button>
              ))}
            </Radio.Group>
          </Form.Item>

          {selectedAction ? <p>{selectedAction.description}</p> : null}

          {intent.inventory_task && action !== 'INVENTORY' ? (
            <Alert
              style={{ marginBottom: 16 }}
              type="warning"
              showIcon
              message={`该资产在盘点任务 ${intent.inventory_task.task_name} 中`}
              description={
                intent.inventory_task.pending ? '盘点结果尚未提交。' : '盘点结果已提交。'
              }
              action={
                <Button
                  size="small"
                  onClick={() => navigate(`/inventory/${intent.inventory_task?.task_id}/scan`)}
                >
                  去盘点
                </Button>
              }
            />
          ) : null}

          {action === 'INVENTORY' ? (
            <Button
              type="primary"
              size="large"
              block
              icon={<ScanLine size={16} />}
              onClick={() => navigate(`/inventory/${intent.inventory_task?.task_id}/scan`)}
            >
              进入盘点扫码
            </Button>
          ) : null}

          {action && action !== 'INVENTORY' ? (
            <>
              {isPublicWorkflow ? (
                <Form.Item
                  name="location_id"
                  label="使用地点"
                  rules={[{ required: true, message: '请选择地点' }]}
                >
                  <Select
                    allowClear
                    showSearch
                    optionFilterProp="label"
                    options={locationOptions}
                  />
                </Form.Item>
              ) : isReturnInspection ? (
                <div className="usage-return-destination-grid">
                  <Form.Item
                    name="return_company_id"
                    label="退库后所属公司"
                    rules={[{ required: true, message: '请选择退库后所属公司' }]}
                  >
                    <Select showSearch optionFilterProp="label" options={organizationOptions} />
                  </Form.Item>
                  <Form.Item
                    name="return_usage_company_id"
                    label="退库后使用公司"
                    rules={[{ required: true, message: '请选择退库后使用公司' }]}
                  >
                    <Select showSearch optionFilterProp="label" options={organizationOptions} />
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
                      options={
                        (returnRegionId ? locationsByRegion[returnRegionId] : undefined) ?? []
                      }
                      disabled={!returnRegionId}
                    />
                  </Form.Item>
                </div>
              ) : (
                <Form.Item name="location_id" label="使用地点">
                  <Select
                    allowClear
                    showSearch
                    optionFilterProp="label"
                    options={locationOptions}
                  />
                </Form.Item>
              )}
              {isPublicWorkflow ? (
                <Form.Item
                  name="public_object_id"
                  label="公共使用对象"
                  rules={[{ required: true, message: '请选择公共使用对象' }]}
                >
                  <Select
                    showSearch
                    optionFilterProp="label"
                    options={publicObjectOptions}
                    placeholder={intent.public_object_name || '选择会议室、直播间或其他公共对象'}
                  />
                </Form.Item>
              ) : null}
              {requiresReturnTime ? (
                <Form.Item
                  name="expected_return_at"
                  label="预计归还时间"
                  rules={[{ required: true, message: '请选择预计归还时间' }]}
                >
                  <DatePicker
                    showTime
                    style={{ width: '100%' }}
                    disabledDate={(value) => value.isBefore(dayjs().startOf('day'))}
                  />
                </Form.Item>
              ) : null}
              {showReason ? (
                <Form.Item
                  name="reason"
                  label={isReturnInspection ? '验收说明' : '申请原因'}
                  rules={
                    condition === 'DAMAGED'
                      ? [{ required: true, min: 2, message: '请填写损坏情况' }]
                      : undefined
                  }
                >
                  <Input.TextArea
                    rows={3}
                    maxLength={2000}
                    placeholder={
                      isReturnInspection ? '正常可留空；损坏时说明情况' : '说明使用场景或项目'
                    }
                  />
                </Form.Item>
              ) : null}
              {isReturnInspection ? (
                <Form.Item name="condition" label="验收结果" initialValue="NORMAL">
                  <Radio.Group optionType="button" buttonStyle="solid">
                    <Radio.Button value="NORMAL">{initialCondition.NORMAL}</Radio.Button>
                    <Radio.Button value="DAMAGED">{initialCondition.DAMAGED}</Radio.Button>
                  </Radio.Group>
                </Form.Item>
              ) : null}
              <Button
                type="primary"
                size="large"
                block
                icon={<ScanLine size={16} />}
                loading={submitMutation.isPending}
                onClick={() => submitMutation.mutate(form.getFieldsValue())}
              >
                提交{selectedAction?.label ?? '申请'}
              </Button>
            </>
          ) : null}
        </Form>
      </Card>
    )
  }
}
