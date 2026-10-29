import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import type { CSSProperties, Key } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ColumnsType } from 'antd/es/table'
import type { Dayjs } from 'dayjs'
import dayjs from 'dayjs'
import {
  Alert,
  Button,
  DatePicker,
  Drawer,
  Empty,
  Form,
  Input,
  Modal,
  Progress,
  Radio,
  Select,
  Space,
  Table,
  Tag,
  Upload,
  message,
} from 'antd'
import {
  ArrowRightLeft,
  BellRing,
  CheckCircle2,
  ClipboardCheck,
  Download,
  FileWarning,
  History,
  Plus,
  QrCode,
  RefreshCw,
  ScanLine,
  Settings2,
  ShieldCheck,
  StopCircle,
  UploadCloud,
  UserRoundCog,
} from 'lucide-react'
import BarcodeScanner from '@/components/scanner/BarcodeScanner'
import { administrationApi, masterDataApi, type TreeItem } from '@/api/administration'
import {
  inventoryApi,
  type CreateInventoryTaskPayload,
  type InventoryItem,
  type InventoryScanEvent,
  type InventoryTask,
  type InventoryTaskStatus,
  type SubmitInventoryPayload,
} from '@/api/inventory'
import { useAuthStore } from '@/store/auth'
import { inventoryVersionActionLabel } from '@/utils/displayLabels'
import {
  GlassPanel,
  OperationsHero,
  OperationsMetrics,
  SectionHeading,
  StatusPill,
} from './OperationsUI'

type InventoryTone = 'blue' | 'cyan' | 'green' | 'amber' | 'red' | 'slate' | 'violet'

interface CreateTaskFormValues {
  name: string
  deadline_at: Dayjs
  admin_user_ids: number[]
  organization_ids?: number[]
  location_ids?: number[]
  category_ids?: number[]
  holder_user_ids?: number[]
  manager_user_ids?: number[]
  asset_statuses?: Array<'IDLE' | 'PENDING_RECEIPT' | 'IN_USE' | 'REPAIRING'>
  public_responsible_user_id?: number
  photo_source_mode: 'CAMERA_ONLY' | 'CAMERA_OR_ALBUM'
  min_photo_count: 1 | 2 | 3
  publish: boolean
}

interface SubmitFormValues {
  result: 'FOUND' | 'LOSS'
  location_mode?: 'STANDARD' | 'TEMPORARY'
  actual_location_id?: number
  temporary_location?: string
  loss_reason?: string
  loss_description?: string
  borrowed_by?: string
}

interface SubmissionTarget {
  item: InventoryItem
  scannedValue?: string
}

interface ReviewTarget {
  item: InventoryItem
  resolution: string
  title: string
}

interface TransferTarget {
  item: InventoryItem
  responsibleUserId?: number
  reason: string
}

const statusMeta: Record<InventoryTaskStatus, { label: string; tone: InventoryTone }> = {
  DRAFT: { label: '草稿', tone: 'slate' },
  IN_PROGRESS: { label: '进行中', tone: 'cyan' },
  OVERDUE: { label: '已逾期', tone: 'amber' },
  REVIEWING: { label: '异常处理中', tone: 'violet' },
  COMPLETED: { label: '已完成', tone: 'green' },
  CANCELLED: { label: '已取消', tone: 'slate' },
}

const itemStatusLabel: Record<InventoryItem['status'], string> = {
  PENDING: '待盘点',
  FOUND: '已找到',
  LOSS: '盘亏',
  UNSUBMITTED: '未完成',
  EXEMPTED: '无需盘点',
}

const lossReasonOptions = [
  { value: 'NOT_WITH_ME', label: '不在本人处' },
  { value: 'LENT_TO_OTHERS', label: '借给他人' },
  { value: 'UNDER_REPAIR', label: '送修中' },
  { value: 'TEMPORARILY_MISSING', label: '暂时找不到' },
  { value: 'SUSPECTED_LOST', label: '疑似丢失' },
  { value: 'OTHER', label: '其他' },
]

function flattenTree(items: TreeItem[], depth = 0): Array<{ value: number; label: string }> {
  return items.flatMap((item) => [
    { value: item.id, label: `${'　'.repeat(depth)}${item.name}` },
    ...flattenTree(item.children ?? [], depth + 1),
  ])
}

function formatDeadline(value?: string | null): string {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '暂无截止时间'
}

async function prepareInventoryPhoto(
  file: File,
  taskName: string,
  assetCode: string,
  submitter: string,
): Promise<File> {
  if (!['image/jpeg', 'image/png'].includes(file.type)) return file
  if (typeof createImageBitmap !== 'function') return file
  const bitmap = await createImageBitmap(file)
  const maxEdge = 2200
  const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(bitmap.width * scale))
  canvas.height = Math.max(1, Math.round(bitmap.height * scale))
  const context = canvas.getContext('2d')
  if (!context) return file
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  const lines = [
    taskName,
    `资产 ${assetCode}`,
    `提交人 ${submitter}`,
    dayjs().format('YYYY-MM-DD HH:mm:ss'),
  ]
  const fontSize = Math.max(18, Math.round(canvas.width / 42))
  const padding = fontSize
  const lineHeight = Math.round(fontSize * 1.35)
  const panelHeight = lineHeight * lines.length + padding * 1.2
  context.fillStyle = 'rgba(12, 20, 34, 0.62)'
  context.fillRect(0, canvas.height - panelHeight, canvas.width, panelHeight)
  context.font = `600 ${fontSize}px -apple-system, BlinkMacSystemFont, sans-serif`
  context.fillStyle = 'rgba(255, 255, 255, 0.94)'
  lines.forEach((line, index) =>
    context.fillText(
      line,
      padding,
      canvas.height - panelHeight + padding + lineHeight * (index + 0.65),
    ),
  )
  let quality = 0.86
  let blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, 'image/jpeg', quality),
  )
  while (blob && blob.size > 2 * 1024 * 1024 && quality > 0.5) {
    quality -= 0.08
    blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', quality),
    )
  }
  bitmap.close()
  return blob
    ? new File([blob], `${file.name.replace(/\.[^.]+$/, '')}-inventory.jpg`, { type: 'image/jpeg' })
    : file
}

export default function Inventory() {
  const queryClient = useQueryClient()
  const location = useLocation()
  const navigate = useNavigate()
  const currentUser = useAuthStore((state) => state.user)
  const canCreate = currentUser?.permissions?.includes('inventory:create') ?? false
  const [createOpen, setCreateOpen] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null)
  const [scannerOpen, setScannerOpen] = useState(false)
  const [submission, setSubmission] = useState<SubmissionTarget | null>(null)
  const [photoFiles, setPhotoFiles] = useState<File[]>([])
  const [selectedItemIds, setSelectedItemIds] = useState<Key[]>([])
  const [adminMarkOpen, setAdminMarkOpen] = useState(false)
  const [adminMarkReason, setAdminMarkReason] = useState('')
  const [reviewTarget, setReviewTarget] = useState<ReviewTarget | null>(null)
  const [reviewReason, setReviewReason] = useState('')
  const [cancelOpen, setCancelOpen] = useState(false)
  const [cancelReason, setCancelReason] = useState('')
  const [reopenOpen, setReopenOpen] = useState(false)
  const [reopenReason, setReopenReason] = useState('')
  const [reopenDeadline, setReopenDeadline] = useState<Dayjs | null>(dayjs().add(3, 'day'))
  const [settingsOpen, setSettingsOpen] = useState<'admins' | 'deadline' | null>(null)
  const [settingsReason, setSettingsReason] = useState('')
  const [settingsDeadline, setSettingsDeadline] = useState<Dayjs | null>(null)
  const [settingsAdminIds, setSettingsAdminIds] = useState<number[]>([])
  const [transferTarget, setTransferTarget] = useState<TransferTarget | null>(null)
  const [createForm] = Form.useForm<CreateTaskFormValues>()
  const [submitForm] = Form.useForm<SubmitFormValues>()

  const quickAction = location.state as { createTask?: boolean; scanInventory?: boolean } | null

  useEffect(() => {
    if (!quickAction?.createTask || !canCreate) return
    setCreateOpen(true)
    createForm.setFieldsValue({
      deadline_at: dayjs().add(7, 'day'),
      admin_user_ids: currentUser ? [currentUser.id] : [],
      photo_source_mode: 'CAMERA_OR_ALBUM',
      min_photo_count: 1,
      publish: true,
    })
    navigate(location.pathname, { replace: true, state: null })
  }, [canCreate, createForm, currentUser, location.pathname, navigate, quickAction?.createTask])

  const overviewQuery = useQuery({
    queryKey: ['inventory-overview'],
    queryFn: inventoryApi.overview,
  })
  const myPendingItemsQuery = useQuery({
    queryKey: ['inventory-my-pending-items', currentUser?.id],
    queryFn: inventoryApi.myPendingItems,
    enabled: currentUser !== null,
  })
  const tasksQuery = useQuery({
    queryKey: ['inventory-tasks'],
    queryFn: () => inventoryApi.tasks(),
  })
  useEffect(() => {
    if (!quickAction?.scanInventory || tasksQuery.isLoading) return

    const target = tasksQuery.data?.items.find((task) =>
      ['IN_PROGRESS', 'OVERDUE'].includes(task.status),
    )
    if (target) {
      setSelectedTaskId(target.id)
      setScannerOpen(true)
    } else {
      void message.info('当前没有可提交的进行中盘点任务')
    }
    navigate(location.pathname, { replace: true, state: null })
  }, [
    location.pathname,
    navigate,
    quickAction?.scanInventory,
    tasksQuery.data,
    tasksQuery.isLoading,
  ])
  const selectedTask = useMemo(
    () => tasksQuery.data?.items.find((task) => task.id === selectedTaskId) ?? null,
    [selectedTaskId, tasksQuery.data],
  )
  const itemsQuery = useQuery({
    queryKey: ['inventory-items', selectedTaskId],
    queryFn: () => inventoryApi.items(selectedTaskId as number),
    enabled: selectedTaskId !== null && drawerOpen,
  })
  const scanEventsQuery = useQuery({
    queryKey: ['inventory-scan-events', selectedTaskId],
    queryFn: () => inventoryApi.scanEvents(selectedTaskId as number),
    enabled: selectedTaskId !== null && drawerOpen && Boolean(selectedTask?.can_manage),
  })
  const usersQuery = useQuery({
    queryKey: ['administration-users'],
    queryFn: () => administrationApi.users(0, 100),
    enabled:
      createOpen ||
      settingsOpen === 'admins' ||
      transferTarget !== null ||
      Boolean(drawerOpen && selectedTask?.can_manage),
  })
  const organizationsQuery = useQuery({
    queryKey: ['master-data', 'organizations'],
    queryFn: masterDataApi.organizations,
    enabled: createOpen,
  })
  const categoriesQuery = useQuery({
    queryKey: ['master-data', 'categories'],
    queryFn: masterDataApi.categories,
    enabled: createOpen,
  })
  const locationsQuery = useQuery({
    queryKey: ['master-data', 'locations'],
    queryFn: masterDataApi.locations,
    enabled: createOpen || submission !== null,
  })

  const refreshInventory = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['inventory-overview'] }),
      queryClient.invalidateQueries({ queryKey: ['inventory-tasks'] }),
      queryClient.invalidateQueries({ queryKey: ['inventory-items'] }),
      queryClient.invalidateQueries({ queryKey: ['inventory-my-pending-items'] }),
      queryClient.invalidateQueries({ queryKey: ['inventory-scan-events'] }),
      queryClient.invalidateQueries({ queryKey: ['asset-dashboard'] }),
    ])
  }

  const createMutation = useMutation({
    mutationFn: inventoryApi.createTask,
    onSuccess: async (task) => {
      message.success(`盘点任务 ${task.task_no} 已创建`)
      setCreateOpen(false)
      createForm.resetFields()
      await refreshInventory()
      setSelectedTaskId(task.id)
      setDrawerOpen(true)
    },
  })

  const scanMutation = useMutation({
    mutationFn: ({ taskId, value }: { taskId: number; value: string }) =>
      inventoryApi.scan(taskId, value),
    onSuccess: (result) => {
      message[result.outcome === 'MATCHED' ? 'success' : 'warning'](result.message)
      if (result.outcome === 'MATCHED' && result.item) {
        setScannerOpen(false)
        setSubmission({ item: result.item, scannedValue: result.asset_code })
        submitForm.setFieldsValue({ result: 'FOUND', location_mode: 'STANDARD' })
      }
    },
  })

  const submitMutation = useMutation({
    mutationFn: async ({
      target,
      values,
    }: {
      target: SubmissionTarget
      values: SubmitFormValues
    }) => {
      const photoIds: number[] = []
      if (values.result === 'FOUND') {
        for (const file of photoFiles) {
          const processedFile = await prepareInventoryPhoto(
            file,
            selectedTask?.name ?? '资产盘点',
            target.item.asset_code,
            currentUser?.nickname || currentUser?.username || '当前用户',
          )
          const photo = await inventoryApi.uploadPhoto(
            target.item.task_id,
            target.item.id,
            processedFile,
          )
          photoIds.push(photo.id)
        }
      }
      const payload: SubmitInventoryPayload = {
        result: values.result,
        scanned_value: target.scannedValue ?? null,
        actual_location_id:
          values.result === 'FOUND' && values.location_mode === 'STANDARD'
            ? values.actual_location_id
            : null,
        temporary_location:
          values.result === 'FOUND' && values.location_mode === 'TEMPORARY'
            ? values.temporary_location
            : null,
        photo_ids: photoIds,
        loss_reason: values.result === 'LOSS' ? values.loss_reason : null,
        loss_description: values.result === 'LOSS' ? values.loss_description : null,
        borrowed_by: values.result === 'LOSS' ? values.borrowed_by : null,
      }
      return inventoryApi.submitItem(target.item.task_id, target.item.id, payload)
    },
    onSuccess: async () => {
      message.success('盘点结果已提交')
      setSubmission(null)
      setPhotoFiles([])
      submitForm.resetFields()
      await refreshInventory()
    },
  })

  const taskActionMutation = useMutation({
    mutationFn: async (action: {
      type: 'publish' | 'end' | 'complete' | 'cancel' | 'admin-mark' | 'reopen'
      task: InventoryTask
    }) => {
      if (action.type === 'publish') return inventoryApi.publish(action.task.id)
      if (action.type === 'end')
        return inventoryApi.endCollection(action.task.id, action.task.counts.pending)
      if (action.type === 'complete') return inventoryApi.complete(action.task.id)
      if (action.type === 'cancel') return inventoryApi.cancel(action.task.id, cancelReason)
      if (action.type === 'admin-mark')
        return inventoryApi.adminMark(
          action.task.id,
          selectedItemIds.map((value) => Number(value)),
          adminMarkReason,
        )
      if (!reopenDeadline) throw new Error('请选择新的截止时间')
      return inventoryApi.reopen(
        action.task.id,
        selectedItemIds.map((value) => Number(value)),
        reopenDeadline.toISOString(),
        reopenReason,
      )
    },
    onSuccess: async (_, action) => {
      const labels = {
        publish: '任务已发布',
        end: '已结束收集，进入异常处理',
        complete: '盘点任务已完成',
        cancel: '盘点任务已取消',
        'admin-mark': '已完成管理员代确认',
        reopen: '已重新开放选中的盘点资产',
      }
      message.success(labels[action.type])
      setAdminMarkOpen(false)
      setCancelOpen(false)
      setReopenOpen(false)
      setAdminMarkReason('')
      setCancelReason('')
      setReopenReason('')
      setSelectedItemIds([])
      await refreshInventory()
    },
  })

  const resolveMutation = useMutation({
    mutationFn: ({ target, reason }: { target: ReviewTarget; reason: string }) =>
      target.resolution === 'RETURNED'
        ? inventoryApi.returnItem(target.item.task_id, target.item.id, reason)
        : inventoryApi.resolveItem(target.item.task_id, target.item.id, target.resolution, reason),
    onSuccess: async (_, variables) => {
      message.success(
        variables.target.resolution === 'RETURNED' ? '已退回员工修改' : '异常处理结果已保存',
      )
      setReviewTarget(null)
      setReviewReason('')
      await refreshInventory()
    },
  })

  const settingsMutation = useMutation({
    mutationFn: async () => {
      if (!selectedTask || !settingsOpen) throw new Error('未选择盘点任务')
      if (settingsOpen === 'admins') {
        return inventoryApi.updateAdmins(selectedTask.id, settingsAdminIds, settingsReason)
      }
      if (!settingsDeadline) throw new Error('请选择新的截止时间')
      return inventoryApi.updateDeadline(
        selectedTask.id,
        settingsDeadline.toISOString(),
        settingsReason,
      )
    },
    onSuccess: async () => {
      message.success(settingsOpen === 'admins' ? '盘点管理员已更新' : '截止时间已更新')
      setSettingsOpen(null)
      setSettingsReason('')
      await refreshInventory()
    },
  })

  const withdrawMutation = useMutation({
    mutationFn: (item: InventoryItem) =>
      inventoryApi.withdrawItem(item.task_id, item.id, '员工主动撤回并重新盘点'),
    onSuccess: async () => {
      message.success('盘点结果已撤回，可以重新扫码提交')
      await refreshInventory()
    },
  })

  const transferMutation = useMutation({
    mutationFn: (target: TransferTarget) => {
      if (!target.responsibleUserId) throw new Error('请选择新的盘点责任人')
      return inventoryApi.transferResponsibility(
        target.item.task_id,
        target.item.id,
        target.responsibleUserId,
        target.reason,
      )
    },
    onSuccess: async () => {
      message.success('盘点责任已转交')
      setTransferTarget(null)
      await refreshInventory()
    },
  })

  const surplusMutation = useMutation({
    mutationFn: ({
      event,
      resolution,
    }: {
      event: InventoryScanEvent
      resolution: 'SURPLUS' | 'IGNORED'
    }) =>
      inventoryApi.resolveSurplus(
        selectedTaskId as number,
        event.id,
        resolution,
        resolution === 'SURPLUS'
          ? '管理员确认任务外扫码资产为盘盈'
          : '管理员确认该扫码记录无需纳入盘点',
      ),
    onSuccess: async () => {
      message.success('扫码异常处理结果已保存')
      await refreshInventory()
    },
  })

  const reminderMutation = useMutation({
    mutationFn: ({ taskId, userIds }: { taskId: number; userIds: number[] }) =>
      inventoryApi.sendReminders(taskId, userIds),
    onSuccess: (result) => {
      message.success(`已将 ${result.recipient_count} 人加入飞书催办队列`)
    },
  })

  const downloadReport = async () => {
    if (!selectedTask) return
    const blob = await inventoryApi.report(selectedTask.id)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${selectedTask.task_no}-盘点报告.xlsx`
    anchor.click()
    URL.revokeObjectURL(url)
    message.success('盘点报告已生成')
  }

  const showVersions = async (item: InventoryItem) => {
    const versions = await inventoryApi.resultVersions(item.task_id, item.id)
    Modal.info({
      title: `${item.asset_code} · 结果版本`,
      width: 680,
      content: (
        <div className="inventory-version-list">
          {versions.length ? (
            versions.map((version) => (
              <div key={version.id}>
                <strong>
                  V{version.version_no} · {inventoryVersionActionLabel(version.action)}
                </strong>
                <span>
                  {version.changed_by_name || `用户 ${version.changed_by}`} ·{' '}
                  {dayjs(version.created_at).format('YYYY-MM-DD HH:mm:ss')}
                </span>
                {version.reason ? <p>{version.reason}</p> : null}
              </div>
            ))
          ) : (
            <Empty description="暂无结果版本" />
          )}
        </div>
      ),
    })
  }

  const openTask = (task: InventoryTask) => {
    setSelectedTaskId(task.id)
    setSelectedItemIds([])
    setDrawerOpen(true)
  }

  const activeTask = tasksQuery.data?.items.find((task) =>
    ['IN_PROGRESS', 'OVERDUE'].includes(task.status),
  )
  const overview = overviewQuery.data
  const taskItems = itemsQuery.data?.items ?? []
  const myPendingItems = myPendingItemsQuery.data ?? []
  const locationOptions = flattenTree(locationsQuery.data ?? [])

  const startScan = (task?: InventoryTask | null) => {
    const target = task ?? activeTask
    if (!target) {
      message.info('当前没有可提交的进行中盘点任务')
      return
    }
    setSelectedTaskId(target.id)
    setScannerOpen(true)
  }

  const showReview = (item: InventoryItem, resolution: string, title: string) => {
    setReviewReason('')
    setReviewTarget({ item, resolution, title })
  }

  const openSettings = (kind: 'admins' | 'deadline') => {
    if (!selectedTask) return
    setSettingsReason('')
    setSettingsAdminIds(selectedTask.admin_user_ids)
    setSettingsDeadline(dayjs(selectedTask.deadline_at))
    setSettingsOpen(kind)
  }

  const confirmReminders = () => {
    if (!selectedTask) return
    const selectedIds = new Set(selectedItemIds.map((value) => Number(value)))
    const userIds = Array.from(
      new Set(
        taskItems
          .filter((item) => !selectedIds.size || selectedIds.has(item.id))
          .filter((item) => item.status === 'PENDING' || item.review_status === 'RETURNED')
          .map((item) => item.responsible_user_id),
      ),
    )
    Modal.confirm({
      title: selectedIds.size ? '催办选中资产的责任人？' : '催办全部未完成人员？',
      content: userIds.length
        ? `将向 ${userIds.length} 名未完成人员生成飞书催办记录。当前环境会先进入本地飞书发送队列。`
        : '当前范围没有可催办的未完成人员。',
      okText: '确认催办',
      okButtonProps: { disabled: !userIds.length },
      onOk: () => reminderMutation.mutateAsync({ taskId: selectedTask.id, userIds }),
    })
  }

  const columns: ColumnsType<InventoryItem> = [
    {
      title: '资产',
      key: 'asset',
      fixed: 'left',
      width: 220,
      render: (_, item) => (
        <div className="inventory-asset-cell">
          <strong>{item.asset_name}</strong>
          <span>{item.asset_code}</span>
        </div>
      ),
    },
    {
      title: '责任人',
      dataIndex: 'holder_name',
      width: 110,
      render: (value) => value || '公共资产责任人',
    },
    {
      title: '台账地点',
      dataIndex: 'ledger_location_name',
      width: 150,
      render: (value) => value || '未登记',
    },
    {
      title: '盘点结果',
      key: 'status',
      width: 130,
      render: (_, item) => (
        <Space size={4} wrap>
          <Tag
            color={
              item.status === 'FOUND' ? 'green' : item.status === 'PENDING' ? 'blue' : 'orange'
            }
          >
            {itemStatusLabel[item.status]}
          </Tag>
          {item.location_result === 'DIFFERENT' ? <Tag color="gold">地点差异</Tag> : null}
          {item.location_result === 'TEMPORARY' ? <Tag color="purple">临时地点</Tag> : null}
          {item.review_status === 'RETURNED' ? <Tag color="magenta">已退回</Tag> : null}
        </Space>
      ),
    },
    {
      title: '实际地点',
      dataIndex: 'actual_location_text',
      width: 150,
      render: (value) => value || '—',
    },
    { title: '照片', key: 'photos', width: 80, render: (_, item) => `${item.photos.length} 张` },
    {
      title: '方式',
      dataIndex: 'submission_method',
      width: 110,
      render: (value) =>
        value === 'ADMIN_MARKED' ? '管理员代确认' : value === 'SCANNED' ? '真实扫码' : '—',
    },
    {
      title: '成套进度',
      key: 'suite',
      width: 130,
      render: (_, item) =>
        item.suite_progress ? (
          <div className="inventory-suite-progress">
            <span>
              {item.suite_progress.checked} / {item.suite_progress.total}
            </span>
            <Progress
              percent={Math.round(
                (item.suite_progress.checked / Math.max(item.suite_progress.total, 1)) * 100,
              )}
              showInfo={false}
              size="small"
            />
          </div>
        ) : (
          '单件'
        ),
    },
    {
      title: '操作',
      key: 'action',
      fixed: 'right',
      width: 310,
      render: (_, item) => (
        <Space size={4} wrap className="inventory-row-actions">
          {item.can_submit && item.status === 'PENDING' ? (
            <Button
              size="small"
              danger
              onClick={() => {
                setSubmission({ item })
                submitForm.setFieldsValue({ result: 'LOSS' })
              }}
            >
              报盘亏
            </Button>
          ) : null}
          {selectedTask?.can_manage &&
          ['IN_PROGRESS', 'OVERDUE'].includes(selectedTask.status) &&
          item.submission_method === 'SCANNED' &&
          ['FOUND', 'LOSS'].includes(item.status) ? (
            <Button size="small" onClick={() => showReview(item, 'RETURNED', '退回员工修改')}>
              退回修改
            </Button>
          ) : null}
          {selectedTask?.can_manage &&
          selectedTask.status === 'REVIEWING' &&
          item.status === 'LOSS' &&
          item.review_status !== 'RESOLVED' ? (
            <Button size="small" onClick={() => showReview(item, 'CONFIRMED_LOSS', '确认盘亏')}>
              确认盘亏
            </Button>
          ) : null}
          {selectedTask?.can_manage &&
          selectedTask.status === 'REVIEWING' &&
          item.status === 'UNSUBMITTED' ? (
            <>
              <Button size="small" onClick={() => showReview(item, 'CONFIRMED_LOSS', '转为盘亏')}>
                转盘亏
              </Button>
              <Button size="small" onClick={() => showReview(item, 'EXEMPTED', '标记无需盘点')}>
                无需盘点
              </Button>
            </>
          ) : null}
          {selectedTask?.can_manage &&
          selectedTask.status === 'REVIEWING' &&
          item.status === 'FOUND' &&
          item.review_status === 'PENDING' ? (
            <Button
              size="small"
              onClick={() => showReview(item, 'LOCATION_RECORDED', '确认地点差异')}
            >
              处理地点
            </Button>
          ) : null}
          {item.submission_method === 'SCANNED' &&
          item.submitted_by === currentUser?.id &&
          ['IN_PROGRESS', 'OVERDUE'].includes(selectedTask?.status ?? '') &&
          ['FOUND', 'LOSS'].includes(item.status) ? (
            <Button
              size="small"
              onClick={() =>
                Modal.confirm({
                  title: `撤回 ${item.asset_code} 的盘点结果？`,
                  content: '撤回后需要重新扫码并提交，原结果会保留在版本记录中。',
                  okText: '确认撤回',
                  onOk: () => withdrawMutation.mutateAsync(item),
                })
              }
            >
              撤回
            </Button>
          ) : null}
          {selectedTask?.can_manage &&
          ['DRAFT', 'IN_PROGRESS', 'OVERDUE'].includes(selectedTask.status) ? (
            <Button
              size="small"
              icon={<ArrowRightLeft size={13} />}
              onClick={() =>
                setTransferTarget({
                  item,
                  responsibleUserId: item.responsible_user_id,
                  reason: '',
                })
              }
            >
              转交
            </Button>
          ) : null}
          {item.result_version_count > 0 ? (
            <Button
              size="small"
              icon={<History size={13} />}
              onClick={() => void showVersions(item)}
            >
              版本 {item.result_version_count}
            </Button>
          ) : null}
        </Space>
      ),
    },
  ]

  const scanEventColumns: ColumnsType<InventoryScanEvent> = [
    {
      title: '扫描内容',
      dataIndex: 'normalized_asset_code',
      width: 170,
      render: (value, event) => value || event.scanned_value,
    },
    {
      title: '识别资产',
      dataIndex: 'asset_name',
      width: 180,
      render: (value) => value || '系统内未找到资产',
    },
    {
      title: '异常类型',
      dataIndex: 'outcome',
      width: 140,
      render: (value: InventoryScanEvent['outcome']) => {
        const labels: Record<InventoryScanEvent['outcome'], string> = {
          MATCHED: '已匹配',
          OUTSIDE_SCOPE: '任务外资产',
          OUTSIDE_ASSIGNMENT: '非本人负责',
          ALREADY_SUBMITTED: '重复扫描',
          UNKNOWN_ASSET: '未知资产',
        }
        return <Tag color={value === 'UNKNOWN_ASSET' ? 'red' : 'gold'}>{labels[value]}</Tag>
      },
    },
    {
      title: '扫描人',
      dataIndex: 'scanner_name',
      width: 120,
      render: (value) => value || '未知用户',
    },
    {
      title: '扫描时间',
      dataIndex: 'created_at',
      width: 160,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '盘盈决策',
      key: 'resolution',
      fixed: 'right',
      width: 210,
      render: (_, event) => {
        if (!['OUTSIDE_SCOPE', 'UNKNOWN_ASSET'].includes(event.outcome)) return '无需处理'
        if (event.resolution) {
          return (
            <Tag color={event.resolution === 'SURPLUS' ? 'cyan' : 'default'}>
              {event.resolution === 'SURPLUS' ? '已确认为盘盈' : '已忽略'}
            </Tag>
          )
        }
        return (
          <Space size={4} wrap className="inventory-anomaly-actions">
            <Button
              size="small"
              type="primary"
              onClick={() => surplusMutation.mutate({ event, resolution: 'SURPLUS' })}
            >
              确认为盘盈
            </Button>
            <Button
              size="small"
              onClick={() => surplusMutation.mutate({ event, resolution: 'IGNORED' })}
            >
              忽略
            </Button>
          </Space>
        )
      },
    },
  ]

  const createTask = (values: CreateTaskFormValues) => {
    const payload: CreateInventoryTaskPayload = {
      name: values.name,
      deadline_at: values.deadline_at.toISOString(),
      admin_user_ids: values.admin_user_ids,
      organization_ids: values.organization_ids ?? [],
      location_ids: values.location_ids ?? [],
      category_ids: values.category_ids ?? [],
      holder_user_ids: values.holder_user_ids ?? [],
      manager_user_ids: values.manager_user_ids ?? [],
      asset_statuses: values.asset_statuses ?? [],
      public_responsible_user_id: values.public_responsible_user_id,
      photo_source_mode: values.photo_source_mode,
      min_photo_count: values.min_photo_count,
      publish: values.publish,
    }
    createMutation.mutate(payload)
  }

  return (
    <div className="operations-page inventory-page">
      <OperationsHero
        eyebrow="SMART INVENTORY"
        title="用一次扫码，确认资产此刻的位置"
        description="盘点任务、资产快照、扫码、照片、地点差异、盘亏与异常处理已连接正式后端，刷新页面后数据仍会保留。"
        icon={ScanLine}
        tone="cyan"
        actions={
          <>
            <Button
              type="primary"
              size="large"
              icon={<QrCode size={18} />}
              onClick={() => startScan()}
            >
              开始扫码盘点
            </Button>
            {canCreate ? (
              <Button
                size="large"
                icon={<Plus size={17} />}
                onClick={() => {
                  setCreateOpen(true)
                  createForm.setFieldsValue({
                    deadline_at: dayjs().add(7, 'day'),
                    admin_user_ids: currentUser ? [currentUser.id] : [],
                    photo_source_mode: 'CAMERA_OR_ALBUM',
                    min_photo_count: 1,
                    publish: true,
                  })
                }}
              >
                创建盘点任务
              </Button>
            ) : null}
          </>
        }
        aside={
          <div
            className="operations-progress-ring operations-tone--cyan"
            style={{ '--progress': `${overview?.completion_rate ?? 0}%` } as CSSProperties}
          >
            <div>
              <strong>{overview?.completion_rate ?? 0}%</strong>
              <span>当前任务完成率</span>
            </div>
          </div>
        }
      />

      <OperationsMetrics
        items={[
          {
            label: '进行中任务',
            value: overview?.active_tasks ?? 0,
            hint: overview?.next_deadline
              ? `最近截止 ${formatDeadline(overview.next_deadline)}`
              : '当前没有进行中任务',
            tone: 'cyan',
          },
          {
            label: '待盘点资产',
            value: overview?.pending_assets ?? 0,
            hint: `当前应盘 ${overview?.total_assets ?? 0} 件`,
            tone: 'blue',
          },
          {
            label: '异常待处理',
            value: overview?.exception_items ?? 0,
            hint: '包含盘亏、地点差异和未完成',
            tone: overview?.exception_items ? 'red' : 'green',
          },
          {
            label: '已完成盘点',
            value: overview?.checked_assets ?? 0,
            hint: '来自真实盘点任务明细',
            tone: 'green',
          },
        ]}
      />

      <GlassPanel className="inventory-my-assets-panel">
        <SectionHeading
          eyebrow="MY ASSETS"
          title="我需要盘点的资产"
          description="汇总所有进行中盘点任务里指派给当前账号的待盘点资产，可逐件扫码提交，也可报盘亏。"
          action={
            <Button
              type="primary"
              icon={<QrCode size={16} />}
              disabled={!myPendingItems.length}
              onClick={() => startScan()}
            >
              扫码我的资产
            </Button>
          }
        />
        {myPendingItemsQuery.isError ? (
          <Alert type="error" showIcon message="我的待盘点资产加载失败" />
        ) : null}
        {myPendingItemsQuery.isLoading ? (
          <div className="operations-loading">正在加载我的待盘点资产…</div>
        ) : !myPendingItems.length ? (
          <Empty description="当前没有指派给您的待盘点资产" />
        ) : (
          <div className="inventory-my-assets-list">
            {myPendingItems.map((item) => {
              const task = tasksQuery.data?.items.find((value) => value.id === item.task_id)
              return (
                <article key={`${item.task_id}-${item.id}`} className="inventory-my-asset">
                  <div className="inventory-my-asset__content">
                    <strong>{item.asset_name}</strong>
                    <span>
                      {item.asset_code} · {item.category_name || '未分类'} ·{' '}
                      {item.ledger_location_name || '地点未登记'}
                    </span>
                    <span>
                      {task ? `${task.name} · ${task.task_no}` : `盘点任务 ${item.task_id}`}
                      {task ? ` · 截止 ${formatDeadline(task.deadline_at)}` : ''}
                    </span>
                  </div>
                  <div className="inventory-my-asset__actions">
                    <Tag color="blue">待盘点</Tag>
                    <Button size="small" onClick={() => startScan(task)}>
                      扫码盘点
                    </Button>
                    <Button
                      size="small"
                      danger
                      onClick={() => {
                        setSelectedTaskId(item.task_id)
                        setSubmission({ item })
                        submitForm.setFieldsValue({ result: 'LOSS' })
                      }}
                    >
                      报盘亏
                    </Button>
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </GlassPanel>

      <div className="operations-split inventory-main-grid">
        <GlassPanel>
          <SectionHeading
            eyebrow="LIVE TASKS"
            title="盘点任务"
            description="任务范围在创建时生成快照，后续台账变化不会改动本次应盘清单。"
            action={
              <Button
                icon={<RefreshCw size={16} />}
                loading={tasksQuery.isFetching}
                onClick={() => void refreshInventory()}
              >
                刷新
              </Button>
            }
          />
          {tasksQuery.isError ? <Alert type="error" showIcon message="盘点任务加载失败" /> : null}
          {!tasksQuery.isLoading && !tasksQuery.data?.items.length ? (
            <Empty description="暂无真实盘点任务，创建后才会显示数据" />
          ) : (
            <div className="operations-task-list">
              {(tasksQuery.data?.items ?? []).map((task) => {
                const meta = statusMeta[task.status]
                return (
                  <button
                    type="button"
                    key={task.id}
                    className={`operations-task inventory-task-button operations-tone--${meta.tone}`}
                    onClick={() => openTask(task)}
                  >
                    <div className="operations-task__progress">{task.progress}%</div>
                    <div className="operations-task__content">
                      <strong>{task.name}</strong>
                      <span>
                        {task.task_no} · 管理员：{task.admins.map((admin) => admin.name).join('、')}
                      </span>
                      <Progress percent={task.progress} showInfo={false} size={['100%', 6]} />
                    </div>
                    <div className="operations-task__aside">
                      <StatusPill label={meta.label} tone={meta.tone} />
                      <small>截止 {formatDeadline(task.deadline_at)}</small>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </GlassPanel>

        <GlassPanel>
          <SectionHeading
            eyebrow="CONTROL CENTER"
            title="盘点规则"
            description="当前页面严格按建设方案执行的关键规则。"
          />
          <div className="inventory-rule-list">
            <div className="operations-card operations-tone--cyan">
              <span className="operations-card__icon">
                <QrCode size={21} />
              </span>
              <h3>员工必须真实扫码</h3>
              <p>正常盘点必须先由摄像头识别资产标签，再填写地点并上传任务要求数量的照片。</p>
            </div>
            <div className="operations-card operations-tone--amber">
              <span className="operations-card__icon">
                <FileWarning size={21} />
              </span>
              <h3>地点差异独立处理</h3>
              <p>
                资产已找到仍记为“已找到 /
                在场”，地点不同或临时地点单独进入异常清单，不直接修改台账。
              </p>
            </div>
            <div className="operations-card operations-tone--green">
              <span className="operations-card__icon">
                <ShieldCheck size={21} />
              </span>
              <h3>任务快照可追溯</h3>
              <p>盘点清单、责任人、提交方式、管理员原因和最终处理结果均保存到后端。</p>
            </div>
          </div>
        </GlassPanel>
      </div>

      <Modal
        title="创建盘点任务"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => createForm.submit()}
        confirmLoading={createMutation.isPending}
        width={720}
        okText="创建任务"
      >
        <Form form={createForm} layout="vertical" onFinish={createTask}>
          <div className="inventory-form-grid">
            <Form.Item
              name="name"
              label="任务名称"
              rules={[{ required: true }, { min: 2, max: 255 }]}
            >
              <Input placeholder="例如：2026 年第三季度资产盘点" />
            </Form.Item>
            <Form.Item name="deadline_at" label="软截止时间" rules={[{ required: true }]}>
              <DatePicker
                showTime
                style={{ width: '100%' }}
                disabledDate={(date) => date.isBefore(dayjs(), 'day')}
              />
            </Form.Item>
            <Form.Item
              name="admin_user_ids"
              label="盘点管理员（至少一名）"
              rules={[{ required: true }]}
            >
              <Select
                mode="multiple"
                options={(usersQuery.data?.items ?? [])
                  .filter((user) => user.enabled !== false)
                  .map((user) => ({ value: user.id, label: user.nickname || user.username }))}
              />
            </Form.Item>
            <Form.Item name="public_responsible_user_id" label="公共资产默认责任人">
              <Select
                allowClear
                options={(usersQuery.data?.items ?? [])
                  .filter((user) => user.enabled !== false)
                  .map((user) => ({ value: user.id, label: user.nickname || user.username }))}
              />
            </Form.Item>
            <Form.Item name="organization_ids" label="所属公司 / 部门范围">
              <Select
                mode="multiple"
                allowClear
                placeholder="不选表示当前权限内全部"
                options={flattenTree(organizationsQuery.data ?? [])}
              />
            </Form.Item>
            <Form.Item name="category_ids" label="资产分类范围">
              <Select
                mode="multiple"
                allowClear
                placeholder="不选表示全部分类"
                options={flattenTree(categoriesQuery.data ?? [])}
              />
            </Form.Item>
            <Form.Item name="location_ids" label="台账地点范围">
              <Select
                mode="multiple"
                allowClear
                placeholder="不选表示全部地点"
                options={locationOptions}
              />
            </Form.Item>
            <Form.Item name="holder_user_ids" label="使用人范围">
              <Select
                mode="multiple"
                allowClear
                placeholder="不选表示全部使用人"
                options={(usersQuery.data?.items ?? []).map((user) => ({
                  value: user.id,
                  label: user.nickname || user.username,
                }))}
              />
            </Form.Item>
            <Form.Item name="manager_user_ids" label="责任管理员范围">
              <Select
                mode="multiple"
                allowClear
                placeholder="不选表示全部责任管理员"
                options={(usersQuery.data?.items ?? []).map((user) => ({
                  value: user.id,
                  label: user.nickname || user.username,
                }))}
              />
            </Form.Item>
            <Form.Item name="asset_statuses" label="资产状态范围">
              <Select
                mode="multiple"
                allowClear
                placeholder="不选表示全部可盘状态"
                options={[
                  { value: 'IDLE', label: '闲置' },
                  { value: 'PENDING_RECEIPT', label: '领用待确认' },
                  { value: 'IN_USE', label: '使用中' },
                  { value: 'REPAIRING', label: '维修中' },
                ]}
              />
            </Form.Item>
            <Form.Item name="photo_source_mode" label="照片来源" rules={[{ required: true }]}>
              <Radio.Group
                options={[
                  { value: 'CAMERA_ONLY', label: '仅现场拍照' },
                  { value: 'CAMERA_OR_ALBUM', label: '相机或相册' },
                ]}
              />
            </Form.Item>
            <Form.Item name="min_photo_count" label="每件最少照片" rules={[{ required: true }]}>
              <Select options={[1, 2, 3].map((value) => ({ value, label: `${value} 张` }))} />
            </Form.Item>
            <Form.Item name="publish" label="创建后状态" rules={[{ required: true }]}>
              <Radio.Group
                options={[
                  { value: true, label: '立即发布' },
                  { value: false, label: '保存草稿' },
                ]}
              />
            </Form.Item>
          </div>
        </Form>
      </Modal>

      <Drawer
        title={selectedTask ? `${selectedTask.name} · ${selectedTask.task_no}` : '盘点任务'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width="min(1180px, 96vw)"
      >
        {selectedTask ? (
          <div className="inventory-drawer">
            <div className="inventory-task-summary">
              <StatusPill
                label={statusMeta[selectedTask.status].label}
                tone={statusMeta[selectedTask.status].tone}
              />
              <span>截止 {formatDeadline(selectedTask.deadline_at)}</span>
              <span>最低照片 {selectedTask.min_photo_count} 张</span>
              <span>
                {selectedTask.photo_source_mode === 'CAMERA_ONLY' ? '仅现场拍照' : '允许相册'}
              </span>
            </div>
            <OperationsMetrics
              items={[
                { label: '应盘', value: selectedTask.counts.total, tone: 'blue' },
                { label: '已找到', value: selectedTask.counts.found, tone: 'green' },
                { label: '盘亏', value: selectedTask.counts.loss, tone: 'red' },
                { label: '未完成', value: selectedTask.counts.unsubmitted, tone: 'amber' },
              ]}
            />
            <div className="inventory-toolbar">
              <Space wrap className="inventory-command-strip">
                {['IN_PROGRESS', 'OVERDUE'].includes(selectedTask.status) ? (
                  <Button
                    type="primary"
                    icon={<QrCode size={16} />}
                    onClick={() => startScan(selectedTask)}
                  >
                    扫码盘点
                  </Button>
                ) : null}
                {selectedTask.can_manage && selectedTask.status === 'DRAFT' ? (
                  <Button
                    onClick={() =>
                      taskActionMutation.mutate({ type: 'publish', task: selectedTask })
                    }
                  >
                    发布任务
                  </Button>
                ) : null}
                {selectedTask.can_manage &&
                ['IN_PROGRESS', 'OVERDUE'].includes(selectedTask.status) ? (
                  <>
                    <Button
                      icon={<BellRing size={16} />}
                      loading={reminderMutation.isPending}
                      onClick={confirmReminders}
                    >
                      {selectedItemIds.length ? '催办选中人员' : '批量催办'}
                    </Button>
                    <Button
                      disabled={!selectedItemIds.length}
                      icon={<ClipboardCheck size={16} />}
                      onClick={() => setAdminMarkOpen(true)}
                    >
                      管理员代确认
                    </Button>
                    <Button
                      danger
                      icon={<StopCircle size={16} />}
                      onClick={() =>
                        Modal.confirm({
                          title: '结束盘点收集？',
                          content: `结束后 ${selectedTask.counts.pending} 件未提交资产会标记为“未完成盘点”，员工将不能继续提交。`,
                          okText: '结束收集',
                          okButtonProps: { danger: true },
                          onOk: () =>
                            taskActionMutation.mutateAsync({ type: 'end', task: selectedTask }),
                        })
                      }
                    >
                      结束收集
                    </Button>
                  </>
                ) : null}
                {selectedTask.can_manage &&
                !['COMPLETED', 'CANCELLED'].includes(selectedTask.status) ? (
                  <Button icon={<UserRoundCog size={16} />} onClick={() => openSettings('admins')}>
                    调整管理员
                  </Button>
                ) : null}
                {selectedTask.can_manage &&
                ['IN_PROGRESS', 'OVERDUE'].includes(selectedTask.status) ? (
                  <Button icon={<Settings2 size={16} />} onClick={() => openSettings('deadline')}>
                    修改截止时间
                  </Button>
                ) : null}
                {selectedTask.can_manage && selectedTask.status === 'REVIEWING' ? (
                  <>
                    <Button disabled={!selectedItemIds.length} onClick={() => setReopenOpen(true)}>
                      重新开放选中项
                    </Button>
                    <Button
                      type="primary"
                      icon={<CheckCircle2 size={16} />}
                      onClick={() =>
                        Modal.confirm({
                          title: '完成盘点任务？',
                          content: '完成后任务数据将锁定，不能再修改盘点结果。',
                          onOk: () =>
                            taskActionMutation.mutateAsync({
                              type: 'complete',
                              task: selectedTask,
                            }),
                        })
                      }
                    >
                      完成盘点
                    </Button>
                  </>
                ) : null}
                {selectedTask.can_manage &&
                !['COMPLETED', 'CANCELLED'].includes(selectedTask.status) ? (
                  <Button danger onClick={() => setCancelOpen(true)}>
                    取消任务
                  </Button>
                ) : null}
                {selectedTask.can_manage ||
                currentUser?.permissions?.includes('inventory:export') ? (
                  <Button icon={<Download size={16} />} onClick={() => void downloadReport()}>
                    导出报告
                  </Button>
                ) : null}
              </Space>
              <span className="inventory-selection-note">已选择 {selectedItemIds.length} 件</span>
            </div>
            <Table<InventoryItem>
              rowKey="id"
              loading={itemsQuery.isLoading}
              dataSource={taskItems}
              columns={columns}
              scroll={{ x: 1520 }}
              pagination={{ pageSize: 20, showSizeChanger: false }}
              rowSelection={
                selectedTask.can_manage
                  ? { selectedRowKeys: selectedItemIds, onChange: setSelectedItemIds }
                  : undefined
              }
            />
            {selectedTask.can_manage ? (
              <section className="inventory-anomaly-section">
                <SectionHeading
                  eyebrow="SCAN EXCEPTIONS"
                  title="任务外扫码与识别异常"
                  description="任务外资产、非本人负责资产、重复扫描和未知标签都会在此留痕，不会直接计入完成结果。"
                />
                <Table<InventoryScanEvent>
                  rowKey="id"
                  loading={scanEventsQuery.isLoading}
                  dataSource={scanEventsQuery.data?.items ?? []}
                  columns={scanEventColumns}
                  scroll={{ x: 980 }}
                  locale={{ emptyText: <Empty description="当前没有扫码异常" /> }}
                  pagination={{ pageSize: 10, showSizeChanger: false }}
                />
              </section>
            ) : null}
          </div>
        ) : null}
      </Drawer>

      <BarcodeScanner
        open={scannerOpen}
        onClose={() => setScannerOpen(false)}
        loading={scanMutation.isPending}
        onDetected={(value) => {
          if (!selectedTaskId) return
          scanMutation.mutate({ taskId: selectedTaskId, value })
        }}
      />

      <Modal
        title={
          submission?.scannedValue
            ? `提交盘点 · ${submission.item.asset_code}`
            : `报告盘亏 · ${submission?.item.asset_code ?? ''}`
        }
        open={submission !== null}
        onCancel={() => {
          setSubmission(null)
          setPhotoFiles([])
          submitForm.resetFields()
        }}
        onOk={() => submitForm.submit()}
        confirmLoading={submitMutation.isPending}
        okText="提交盘点结果"
      >
        {submission ? (
          <Form
            form={submitForm}
            layout="vertical"
            onFinish={(values) => submitMutation.mutate({ target: submission, values })}
          >
            <Form.Item name="result" label="实物结果" rules={[{ required: true }]}>
              <Radio.Group
                disabled={Boolean(submission.scannedValue)}
                options={[
                  { value: 'FOUND', label: '已找到' },
                  { value: 'LOSS', label: '盘亏' },
                ]}
              />
            </Form.Item>
            <Form.Item
              noStyle
              shouldUpdate={(previous, current) => previous.result !== current.result}
            >
              {({ getFieldValue }) =>
                getFieldValue('result') === 'FOUND' ? (
                  <>
                    <Form.Item
                      name="location_mode"
                      label="实际地点类型"
                      rules={[{ required: true }]}
                    >
                      <Radio.Group
                        options={[
                          { value: 'STANDARD', label: '标准地点' },
                          { value: 'TEMPORARY', label: '临时地点' },
                        ]}
                      />
                    </Form.Item>
                    <Form.Item
                      noStyle
                      shouldUpdate={(previous, current) =>
                        previous.location_mode !== current.location_mode
                      }
                    >
                      {({ getFieldValue: getLocationMode }) =>
                        getLocationMode('location_mode') === 'TEMPORARY' ? (
                          <Form.Item
                            name="temporary_location"
                            label="临时地点描述"
                            rules={[{ required: true }]}
                          >
                            <Input.TextArea rows={3} placeholder="填写完整现场位置" />
                          </Form.Item>
                        ) : (
                          <Form.Item
                            name="actual_location_id"
                            label="标准地点"
                            rules={[{ required: true }]}
                          >
                            <Select showSearch optionFilterProp="label" options={locationOptions} />
                          </Form.Item>
                        )
                      }
                    </Form.Item>
                    <Form.Item
                      label={`现场照片（至少 ${selectedTask?.min_photo_count ?? 1} 张，最多 5 张）`}
                      required
                    >
                      <Upload
                        accept="image/jpeg,image/png,image/heic,image/heif"
                        capture={
                          selectedTask?.photo_source_mode === 'CAMERA_ONLY'
                            ? 'environment'
                            : undefined
                        }
                        fileList={photoFiles.map((file) => ({
                          uid: `${file.name}-${file.lastModified}`,
                          name: file.name,
                          status: 'done',
                        }))}
                        beforeUpload={(file) => {
                          setPhotoFiles((current) => [...current, file].slice(0, 5))
                          return false
                        }}
                        onRemove={(file) => {
                          setPhotoFiles((current) =>
                            current.filter(
                              (item) => `${item.name}-${item.lastModified}` !== file.uid,
                            ),
                          )
                        }}
                        maxCount={5}
                      >
                        <Button icon={<UploadCloud size={16} />}>选择或拍摄照片</Button>
                      </Upload>
                    </Form.Item>
                  </>
                ) : (
                  <>
                    <Form.Item name="loss_reason" label="盘亏理由" rules={[{ required: true }]}>
                      <Select options={lossReasonOptions} />
                    </Form.Item>
                    <Form.Item
                      noStyle
                      shouldUpdate={(previous, current) =>
                        previous.loss_reason !== current.loss_reason
                      }
                    >
                      {({ getFieldValue: getReason }) =>
                        getReason('loss_reason') === 'LENT_TO_OTHERS' ? (
                          <Form.Item name="borrowed_by" label="借用人">
                            <Input />
                          </Form.Item>
                        ) : null
                      }
                    </Form.Item>
                    <Form.Item name="loss_description" label="补充说明">
                      <Input.TextArea rows={3} />
                    </Form.Item>
                  </>
                )
              }
            </Form.Item>
          </Form>
        ) : null}
      </Modal>

      <Modal
        title="管理员代确认"
        open={adminMarkOpen}
        onCancel={() => setAdminMarkOpen(false)}
        onOk={() =>
          selectedTask && taskActionMutation.mutate({ type: 'admin-mark', task: selectedTask })
        }
        confirmLoading={taskActionMutation.isPending}
        okButtonProps={{ disabled: adminMarkReason.trim().length < 2 }}
      >
        <Alert
          type="info"
          showIcon
          message={`将直接标记 ${selectedItemIds.length} 件资产为已找到，不要求扫码、地点或照片；原因会永久记录。`}
        />
        <Input.TextArea
          value={adminMarkReason}
          onChange={(event) => setAdminMarkReason(event.target.value)}
          rows={4}
          placeholder="填写直接标记原因"
          style={{ marginTop: 16 }}
        />
      </Modal>

      <Modal
        title={reviewTarget?.title ?? '处理异常'}
        open={reviewTarget !== null}
        onCancel={() => setReviewTarget(null)}
        onOk={() =>
          reviewTarget && resolveMutation.mutate({ target: reviewTarget, reason: reviewReason })
        }
        confirmLoading={resolveMutation.isPending}
        okButtonProps={{ disabled: reviewReason.trim().length < 2 }}
      >
        <Input.TextArea
          value={reviewReason}
          onChange={(event) => setReviewReason(event.target.value)}
          rows={4}
          placeholder="填写处理依据和结果说明"
        />
      </Modal>

      <Modal
        title="取消盘点任务"
        open={cancelOpen}
        onCancel={() => setCancelOpen(false)}
        onOk={() =>
          selectedTask && taskActionMutation.mutate({ type: 'cancel', task: selectedTask })
        }
        confirmLoading={taskActionMutation.isPending}
        okButtonProps={{ danger: true, disabled: cancelReason.trim().length < 2 }}
      >
        <Alert type="warning" showIcon message="取消后保留已有结果、照片和日志，任务不会被删除。" />
        <Input.TextArea
          value={cancelReason}
          onChange={(event) => setCancelReason(event.target.value)}
          rows={4}
          placeholder="填写取消原因"
          style={{ marginTop: 16 }}
        />
      </Modal>

      <Modal
        title="局部重新开放"
        open={reopenOpen}
        onCancel={() => setReopenOpen(false)}
        onOk={() =>
          selectedTask && taskActionMutation.mutate({ type: 'reopen', task: selectedTask })
        }
        confirmLoading={taskActionMutation.isPending}
        okButtonProps={{ disabled: !reopenDeadline || reopenReason.trim().length < 2 }}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={16}>
          <Alert
            type="info"
            showIcon
            message={`仅重新开放选中的 ${selectedItemIds.length} 件资产，其他已完成结果保持不变。`}
          />
          <DatePicker
            showTime
            value={reopenDeadline}
            onChange={(value) => setReopenDeadline(value)}
            style={{ width: '100%' }}
          />
          <Input.TextArea
            value={reopenReason}
            onChange={(event) => setReopenReason(event.target.value)}
            rows={4}
            placeholder="填写重新开放原因"
          />
        </Space>
      </Modal>

      <Modal
        title={settingsOpen === 'admins' ? '调整盘点管理员' : '修改软截止时间'}
        open={settingsOpen !== null}
        className="inventory-settings-modal"
        onCancel={() => {
          setSettingsOpen(null)
          setSettingsReason('')
        }}
        onOk={() => settingsMutation.mutate()}
        confirmLoading={settingsMutation.isPending}
        okText="保存调整"
        okButtonProps={{
          disabled:
            settingsReason.trim().length < 2 ||
            (settingsOpen === 'admins' ? settingsAdminIds.length < 1 : !settingsDeadline),
        }}
      >
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message={
              settingsOpen === 'admins'
                ? '管理员调整立即生效，新增管理员可以查看并处理整项盘点任务。'
                : '截止时间是软截止；到期只标记逾期，不会自动结束员工提交。'
            }
          />
          {settingsOpen === 'admins' ? (
            <Select
              mode="multiple"
              value={settingsAdminIds}
              onChange={setSettingsAdminIds}
              placeholder="选择至少一名盘点管理员"
              options={(usersQuery.data?.items ?? [])
                .filter((user) => user.enabled !== false)
                .map((user) => ({ value: user.id, label: user.nickname || user.username }))}
              style={{ width: '100%' }}
            />
          ) : (
            <DatePicker
              showTime
              value={settingsDeadline}
              onChange={setSettingsDeadline}
              disabledDate={(date) => date.isBefore(dayjs(), 'day')}
              style={{ width: '100%' }}
            />
          )}
          <Input.TextArea
            value={settingsReason}
            onChange={(event) => setSettingsReason(event.target.value)}
            rows={4}
            placeholder="填写调整原因，至少 2 个字"
          />
        </Space>
      </Modal>

      <Modal
        title={transferTarget ? `转交盘点责任 · ${transferTarget.item.asset_code}` : '转交盘点责任'}
        open={transferTarget !== null}
        className="inventory-settings-modal"
        onCancel={() => setTransferTarget(null)}
        onOk={() => transferTarget && transferMutation.mutate(transferTarget)}
        confirmLoading={transferMutation.isPending}
        okText="确认转交"
        okButtonProps={{
          disabled:
            !transferTarget?.responsibleUserId || (transferTarget?.reason.trim().length ?? 0) < 2,
        }}
      >
        {transferTarget ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Alert
              type="warning"
              showIcon
              message="责任转交只改变本次任务的提交人，不会修改正式资产台账。"
            />
            <Select
              value={transferTarget.responsibleUserId}
              onChange={(responsibleUserId) =>
                setTransferTarget((current) =>
                  current ? { ...current, responsibleUserId } : current,
                )
              }
              placeholder="选择新的盘点责任人"
              options={(usersQuery.data?.items ?? [])
                .filter((user) => user.enabled !== false)
                .map((user) => ({ value: user.id, label: user.nickname || user.username }))}
              style={{ width: '100%' }}
            />
            <Input.TextArea
              value={transferTarget.reason}
              onChange={(event) =>
                setTransferTarget((current) =>
                  current ? { ...current, reason: event.target.value } : current,
                )
              }
              rows={4}
              placeholder="填写责任转交原因，至少 2 个字"
            />
          </Space>
        ) : null}
      </Modal>
    </div>
  )
}
