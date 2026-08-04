import { Button, Form, Input, InputNumber, Modal, Select, Spin, Switch, message } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  Boxes,
  Database,
  PencilLine,
  Plus,
  Power,
  Search,
  Trash2,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { assetManagementApi, type PublicUsageObject } from '@/api/assetManagement'
import {
  masterDataApi,
  type DeleteImpact,
  type ReferenceItem,
  type SupplierItem,
  type TreeItem,
} from '@/api/administration'
import StatePanel from '@/components/ui/StatePanel'
import { useAuthStore } from '@/store/auth'
import {
  GlassPanel,
  OperationsHero,
  OperationsMetrics,
  SectionHeading,
  StatusPill,
} from './OperationsUI'

type MasterGroupKey =
  | 'organizations'
  | 'categories'
  | 'locations'
  | 'units'
  | 'sources'
  | 'suppliers'
  | 'public-objects'

type MasterEntity = ReferenceItem | TreeItem | SupplierItem | PublicUsageObject

interface MasterNode {
  id: number
  code: string
  name: string
  detail: string
  status: string
  children: number
  depth: number
  entity: MasterEntity
}

interface MasterGroup {
  key: MasterGroupKey
  label: string
  description: string
  nodes: MasterNode[]
}

interface MasterFormValues {
  code?: string
  name: string
  parent_id?: number | null
  service_life_months?: number
  default_unit_id?: number
  is_selectable?: boolean
  unified_social_credit_code?: string
  contact_name?: string
  contact_phone?: string
  address?: string
  remark?: string
}

interface DeleteTarget {
  kind: 'locations' | 'categories'
  node: MasterNode
}

interface MasterOverview {
  categories: TreeItem[]
  units: ReferenceItem[]
  sources: ReferenceItem[]
  locations: TreeItem[]
  suppliers: SupplierItem[]
  organizations: TreeItem[]
  publicObjects: PublicUsageObject[]
}

const permissionByGroup: Record<MasterGroupKey, string> = {
  organizations: 'organization:manage',
  categories: 'asset-category:manage',
  locations: 'location:manage',
  units: 'unit:manage',
  sources: 'asset-source:manage',
  suppliers: 'supplier:edit',
  'public-objects': 'public-object:manage',
}

function flattenTree(
  items: TreeItem[],
  detail: (item: TreeItem, depth: number) => string,
  depth = 0,
): MasterNode[] {
  return items.flatMap<MasterNode>((item) => [
    {
      id: item.id,
      code: item.code,
      name: item.name,
      detail: detail(item, depth),
      status: item.status,
      children: item.children?.length ?? 0,
      depth,
      entity: item,
    },
    ...flattenTree(item.children ?? [], detail, depth + 1),
  ])
}

function referenceNodes(items: ReferenceItem[], detail: string): MasterNode[] {
  return items.map((item) => ({
    id: item.id,
    code: item.code,
    name: item.name,
    detail,
    status: item.status,
    children: 0,
    depth: 0,
    entity: item,
  }))
}

function supplierNodes(items: SupplierItem[]): MasterNode[] {
  return items.map((item) => ({
    id: item.id,
    code: item.code,
    name: item.name,
    detail: item.contact_name ? `联系人：${item.contact_name}` : '未设置联系人',
    status: item.status,
    children: 0,
    depth: 0,
    entity: item,
  }))
}

function isEnabled(status: string): boolean {
  return ['ENABLED', 'ACTIVE'].includes(status.toUpperCase())
}

function asTreeItem(entity: MasterEntity): TreeItem {
  return entity as TreeItem
}

function asSupplier(entity: MasterEntity): SupplierItem {
  return entity as SupplierItem
}

export default function MasterData() {
  const [activeKey, setActiveKey] = useState<MasterGroupKey>('organizations')
  const [keyword, setKeyword] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [editingNode, setEditingNode] = useState<MasterNode | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null)
  const [deleteImpact, setDeleteImpact] = useState<DeleteImpact | null>(null)
  const [deleteReason, setDeleteReason] = useState('')
  const [deleteImpactLoading, setDeleteImpactLoading] = useState(false)
  const [form] = Form.useForm<MasterFormValues>()
  const queryClient = useQueryClient()
  const permissions = useAuthStore((state) => state.user?.permissions ?? [])
  const query = useQuery({
    queryKey: ['master-data', 'overview'],
    queryFn: async (): Promise<MasterOverview> => {
      const [categories, units, sources, locations, suppliers, organizations, publicObjects] =
        await Promise.all([
          masterDataApi.categories(),
          masterDataApi.units(),
          masterDataApi.sources(),
          masterDataApi.locations(),
          masterDataApi.suppliers(),
          masterDataApi.organizations(),
          assetManagementApi.publicObjects(true),
        ])
      return { categories, units, sources, locations, suppliers, organizations, publicObjects }
    },
  })

  const groups = useMemo<MasterGroup[]>(() => {
    const data = query.data
    return [
      {
        key: 'organizations',
        label: '组织架构',
        description: '维护公司与部门层级，停用节点会保留历史归属。',
        nodes: flattenTree(data?.organizations ?? [], (_item, depth) =>
          depth ? `第 ${depth + 1} 级组织` : '顶级组织',
        ),
      },
      {
        key: 'categories',
        label: '资产分类',
        description: '维护分类层级、默认计量单位和标准使用期限。',
        nodes: flattenTree(
          data?.categories ?? [],
          (item) =>
            `${item.service_life_months ?? '—'} 个月 · 默认单位 ${item.default_unit_id ?? '—'}`,
        ),
      },
      {
        key: 'locations',
        label: '存放地点',
        description: '维护地点层级，并控制节点能否直接存放资产。',
        nodes: flattenTree(data?.locations ?? [], (item) =>
          item.is_selectable ? '可存放资产' : '仅作为层级节点',
        ),
      },
      {
        key: 'units',
        label: '计量单位',
        description: '资产登记与库存统计使用的计量单位。',
        nodes: referenceNodes(data?.units ?? [], '计量单位'),
      },
      {
        key: 'sources',
        label: '资产来源',
        description: '采购、调入等资产来源字典。',
        nodes: referenceNodes(data?.sources ?? [], '资产来源'),
      },
      {
        key: 'suppliers',
        label: '供应商',
        description: '维护采购入库可选择的供应商档案。',
        nodes: supplierNodes(data?.suppliers ?? []),
      },
      {
        key: 'public-objects',
        label: '公共使用对象',
        description: '会议室、前台、直播间等公共资产使用对象。',
        nodes: (data?.publicObjects ?? []).map((item) => ({
          id: item.id,
          code: item.code,
          name: item.name,
          detail: `${item.usage_count} 件资产正在引用`,
          status: item.status,
          children: 0,
          depth: 0,
          entity: item,
        })),
      },
    ]
  }, [query.data])

  const activeGroup = groups.find((group) => group.key === activeKey) ?? groups[0]
  const normalizedKeyword = keyword.trim().toLowerCase()
  const nodes = activeGroup.nodes.filter(
    (node) =>
      !normalizedKeyword ||
      node.name.toLowerCase().includes(normalizedKeyword) ||
      node.code.toLowerCase().includes(normalizedKeyword),
  )
  const activeCount = activeGroup.nodes.filter((node) => isEnabled(node.status)).length
  const totalNodes = groups.reduce((sum, group) => sum + group.nodes.length, 0)
  const canCreate =
    activeKey === 'suppliers'
      ? permissions.includes('supplier:create')
      : permissions.includes(permissionByGroup[activeKey])
  const canEdit = permissions.includes(permissionByGroup[activeKey])
  const canToggle = activeKey === 'suppliers' ? permissions.includes('supplier:disable') : canEdit
  const canDelete =
    (activeKey === 'locations' && permissions.includes('location:delete')) ||
    (activeKey === 'categories' && permissions.includes('asset-category:delete'))

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['master-data'] })
    await queryClient.invalidateQueries({ queryKey: ['asset-reference-data'] })
  }

  const saveMutation = useMutation({
    mutationFn: async (values: MasterFormValues) => {
      const code = values.code?.trim() ?? ''
      const name = values.name.trim()
      if (activeKey === 'public-objects') {
        if (editingNode) return assetManagementApi.updatePublicObject(editingNode.id, { name })
        return assetManagementApi.createPublicObject(name)
      }
      if (activeKey === 'units') {
        if (editingNode) {
          return masterDataApi.updateUnit(editingNode.id, {
            name,
            version: (editingNode.entity as ReferenceItem).version,
          })
        }
        return masterDataApi.createUnit({ code, name })
      }
      if (activeKey === 'sources') {
        if (editingNode) {
          return masterDataApi.updateSource(editingNode.id, {
            name,
            version: (editingNode.entity as ReferenceItem).version,
          })
        }
        return masterDataApi.createSource({ code, name })
      }
      if (activeKey === 'organizations') {
        if (editingNode) {
          return masterDataApi.updateOrganization(editingNode.id, {
            name,
            parent_id: values.parent_id ?? null,
            version: asTreeItem(editingNode.entity).version,
          })
        }
        return masterDataApi.createOrganization({ code, name, parent_id: values.parent_id ?? null })
      }
      if (activeKey === 'locations') {
        const payload = {
          name,
          parent_id: values.parent_id ?? null,
          is_selectable: values.is_selectable ?? true,
        }
        if (editingNode) {
          return masterDataApi.updateLocation(editingNode.id, {
            ...payload,
            version: asTreeItem(editingNode.entity).version,
          })
        }
        return masterDataApi.createLocation(payload)
      }
      if (activeKey === 'categories') {
        const payload = {
          name,
          parent_id: values.parent_id ?? null,
          service_life_months: values.service_life_months ?? 36,
          default_unit_id: values.default_unit_id ?? 0,
        }
        if (editingNode) {
          return masterDataApi.updateCategory(editingNode.id, {
            ...payload,
            version: asTreeItem(editingNode.entity).version,
          })
        }
        return masterDataApi.createCategory({ code, ...payload })
      }
      const supplierPayload = {
        name,
        unified_social_credit_code: values.unified_social_credit_code?.trim() || null,
        contact_name: values.contact_name?.trim() || null,
        contact_phone: values.contact_phone?.trim() || null,
        address: values.address?.trim() || null,
        remark: values.remark?.trim() || null,
      }
      if (editingNode) {
        return masterDataApi.updateSupplier(editingNode.id, {
          ...supplierPayload,
          version: asSupplier(editingNode.entity).version,
        })
      }
      return masterDataApi.createSupplier(supplierPayload)
    },
    onSuccess: async () => {
      setModalOpen(false)
      await refresh()
      void message.success(editingNode ? '基础资料已更新' : '基础资料已创建')
    },
    onError: (error) => void message.error(error instanceof Error ? error.message : '保存失败'),
  })

  const toggleMutation = useMutation({
    mutationFn: async (node: MasterNode) => {
      const enabled = !isEnabled(node.status)
      if (activeKey === 'public-objects') {
        return assetManagementApi.updatePublicObject(node.id, {
          status: enabled ? 'ENABLED' : 'DISABLED',
        })
      }
      if (activeKey === 'units') return masterDataApi.setUnitEnabled(node.id, enabled)
      if (activeKey === 'sources') return masterDataApi.setSourceEnabled(node.id, enabled)
      if (activeKey === 'organizations') {
        return masterDataApi.setOrganizationEnabled(node.id, enabled)
      }
      if (activeKey === 'locations') return masterDataApi.setLocationEnabled(node.id, enabled)
      if (activeKey === 'categories') return masterDataApi.setCategoryEnabled(node.id, enabled)
      return masterDataApi.setSupplierEnabled(node.id, enabled, asSupplier(node.entity).version)
    },
    onSuccess: async () => {
      await refresh()
      void message.success('启停状态已更新')
    },
    onError: (error) => void message.error(error instanceof Error ? error.message : '操作失败'),
  })

  const deleteMutation = useMutation({
    mutationFn: async () => {
      if (!deleteTarget || !deleteImpact) throw new Error('请先检查删除影响')
      const payload = {
        version: deleteImpact.version,
        reason: deleteReason.trim(),
        confirmed: true as const,
      }
      if (deleteTarget.kind === 'locations') {
        return masterDataApi.deleteLocation(deleteTarget.node.id, payload)
      }
      return masterDataApi.deleteCategory(deleteTarget.node.id, payload)
    },
    onSuccess: async () => {
      setDeleteTarget(null)
      setDeleteImpact(null)
      setDeleteReason('')
      await refresh()
      await queryClient.invalidateQueries({ queryKey: ['audit-logs'] })
      void message.success('基础资料已删除，编码不会再次使用')
    },
    onError: (error) => void message.error(error instanceof Error ? error.message : '删除失败'),
  })

  const openDelete = async (node: MasterNode) => {
    if (activeKey !== 'locations' && activeKey !== 'categories') return
    const target: DeleteTarget = { kind: activeKey, node }
    setDeleteTarget(target)
    setDeleteImpact(null)
    setDeleteReason('')
    setDeleteImpactLoading(true)
    try {
      const impact =
        target.kind === 'locations'
          ? await masterDataApi.locationDeleteImpact(node.id)
          : await masterDataApi.categoryDeleteImpact(node.id)
      setDeleteImpact(impact)
    } catch (error) {
      setDeleteTarget(null)
      void message.error(error instanceof Error ? error.message : '删除影响检查失败')
    } finally {
      setDeleteImpactLoading(false)
    }
  }

  const parentOptions = useMemo(
    () =>
      activeGroup.nodes
        .filter((node) => node.id !== editingNode?.id)
        .map((node) => ({
          value: node.id,
          label: `${'— '.repeat(node.depth)}${node.name}（${node.code}）`,
        })),
    [activeGroup.nodes, editingNode?.id],
  )

  const openCreate = () => {
    setEditingNode(null)
    form.resetFields()
    form.setFieldsValue({ is_selectable: true, service_life_months: 36 })
    setModalOpen(true)
  }

  const openEdit = (node: MasterNode) => {
    setEditingNode(node)
    const tree = asTreeItem(node.entity)
    const supplier = asSupplier(node.entity)
    form.setFieldsValue({
      code: node.code,
      name: node.name,
      parent_id: tree.parent_id ?? null,
      service_life_months: tree.service_life_months,
      default_unit_id: tree.default_unit_id,
      is_selectable: tree.is_selectable,
      unified_social_credit_code: supplier.unified_social_credit_code ?? undefined,
      contact_name: supplier.contact_name ?? undefined,
      contact_phone: supplier.contact_phone ?? undefined,
      address: supplier.address ?? undefined,
      remark: supplier.remark ?? undefined,
    })
    setModalOpen(true)
  }

  const requestToggle = (node: MasterNode) => {
    const enabled = isEnabled(node.status)
    if (!enabled) {
      toggleMutation.mutate(node)
      return
    }
    Modal.confirm({
      title: `停用“${node.name}”`,
      content: '停用后不会删除历史引用，但不能继续用于新的业务操作。确认继续吗？',
      okText: '确认停用',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => toggleMutation.mutateAsync(node),
    })
  }

  const modalTitle = `${editingNode ? '编辑' : '新建'}${activeGroup.label}`
  const needsCode =
    !editingNode && !['suppliers', 'public-objects', 'locations'].includes(activeKey)
  const hasParent = ['organizations', 'categories', 'locations'].includes(activeKey)

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow="MASTER DATA"
        title="把每一项基础资料，维护成业务可以信任的标准"
        description="七类基础资料均来自后端；有权限的管理员可以直接新增、编辑和启停。"
        icon={Database}
        tone="amber"
        actions={
          canCreate ? (
            <Button type="primary" size="large" icon={<Plus size={17} />} onClick={openCreate}>
              新建{activeGroup.label}
            </Button>
          ) : undefined
        }
        aside={
          <div className="operations-hero__aside-card">
            <span>基础资料记录</span>
            <strong>{totalNodes}</strong>
            <small>当前七类真实后端数据</small>
          </div>
        }
      />

      <OperationsMetrics
        items={[
          {
            label: '资料类型',
            value: groups.length,
            hint: '组织、分类、地点与字典',
            tone: 'amber',
          },
          {
            label: '当前类型',
            value: activeGroup.nodes.length,
            hint: activeGroup.label,
            tone: 'blue',
          },
          { label: '当前在用', value: activeCount, hint: '可被业务继续选择', tone: 'green' },
          {
            label: '当前停用',
            value: activeGroup.nodes.length - activeCount,
            hint: '历史记录仍然保留',
            tone: 'slate',
          },
        ]}
      />

      <GlassPanel>
        {query.isLoading ? (
          <div className="operations-loading">
            <Spin />
          </div>
        ) : query.isError ? (
          <StatePanel
            mode="error"
            message="基础资料加载失败，请确认后端服务和当前账号权限"
            retryLabel="重新加载"
            onRetry={() => void query.refetch()}
          />
        ) : (
          <div className="operations-master-layout">
            <nav className="operations-master-menu" aria-label="基础资料类型">
              {groups.map((group) => (
                <button
                  key={group.key}
                  type="button"
                  className={group.key === activeGroup.key ? 'is-active' : ''}
                  onClick={() => {
                    setActiveKey(group.key)
                    setKeyword('')
                  }}
                >
                  <span>{group.label}</span>
                  <small>{group.nodes.length}</small>
                </button>
              ))}
            </nav>

            <div>
              <SectionHeading
                eyebrow="DICTIONARY"
                title={activeGroup.label}
                description={activeGroup.description}
                action={
                  <div className="operations-toolbar__filters">
                    <StatusPill label="真实后端数据" tone="green" />
                    {canCreate ? (
                      <Button size="small" icon={<Plus size={14} />} onClick={openCreate}>
                        新增
                      </Button>
                    ) : null}
                  </div>
                }
              />
              <div className="operations-toolbar">
                <Input
                  value={keyword}
                  allowClear
                  prefix={<Search aria-hidden="true" size={15} />}
                  placeholder={`搜索${activeGroup.label}编码或名称`}
                  onChange={(event) => setKeyword(event.target.value)}
                />
                <div className="operations-toolbar__filters">
                  <StatusPill label={`${activeCount} 个在用`} tone="green" />
                  <StatusPill
                    label={`${activeGroup.nodes.length - activeCount} 个停用`}
                    tone="slate"
                  />
                </div>
              </div>
              {nodes.length ? (
                <div className="operations-task-list">
                  {nodes.map((node, index) => (
                    <div
                      key={`${activeKey}-${node.id}`}
                      className={`operations-master-node operations-tone--${index % 2 ? 'cyan' : 'amber'}`}
                      style={{ marginLeft: Math.min(node.depth * 18, 54) }}
                    >
                      <span className="operations-master-node__icon">{node.code.slice(0, 4)}</span>
                      <div className="operations-master-node__content">
                        <strong>{node.name}</strong>
                        <span>
                          {node.code} · {node.detail}
                          {node.children ? ` · ${node.children} 个直接下级` : ''}
                        </span>
                      </div>
                      <div className="operations-master-node__actions">
                        <StatusPill
                          label={isEnabled(node.status) ? '在用' : '停用'}
                          tone={isEnabled(node.status) ? 'green' : 'slate'}
                        />
                        {canEdit ? (
                          <Button
                            type="text"
                            aria-label={`编辑${node.name}`}
                            icon={<PencilLine size={15} />}
                            onClick={() => openEdit(node)}
                          />
                        ) : null}
                        {canToggle ? (
                          <Button
                            type="text"
                            danger={isEnabled(node.status)}
                            aria-label={`${isEnabled(node.status) ? '停用' : '启用'}${node.name}`}
                            icon={<Power size={15} />}
                            loading={toggleMutation.isPending}
                            onClick={() => requestToggle(node)}
                          />
                        ) : null}
                        {canDelete ? (
                          <Button
                            type="text"
                            danger
                            aria-label={`删除${node.name}`}
                            icon={<Trash2 size={15} />}
                            onClick={() => void openDelete(node)}
                          />
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="operations-empty-note">
                  <Boxes size={24} />
                  <br />
                  没有匹配的基础资料
                </div>
              )}
            </div>
          </div>
        )}
      </GlassPanel>

      <Modal
        open={modalOpen}
        title={modalTitle}
        okText={editingNode ? '保存修改' : '确认创建'}
        cancelText="取消"
        className="operations-glass-modal"
        confirmLoading={saveMutation.isPending}
        onOk={() => form.submit()}
        onCancel={() => setModalOpen(false)}
      >
        <Form form={form} layout="vertical" onFinish={(values) => saveMutation.mutate(values)}>
          {needsCode ? (
            <Form.Item
              name="code"
              label="编码"
              rules={[{ required: true, whitespace: true, message: '请输入编码' }]}
            >
              <Input maxLength={64} placeholder="请输入唯一编码" />
            </Form.Item>
          ) : null}
          {activeKey === 'locations' && !editingNode ? (
            <p className="operations-form-note">
              地点编码由系统自动生成（LOC + 6 位流水号），创建后永久不变，删除后也不会复用。
            </p>
          ) : null}
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, whitespace: true, message: '请输入名称' }]}
          >
            <Input maxLength={255} placeholder={`请输入${activeGroup.label}名称`} />
          </Form.Item>
          {hasParent ? (
            <Form.Item name="parent_id" label="上级节点">
              <Select allowClear options={parentOptions} placeholder="不选择则作为顶级节点" />
            </Form.Item>
          ) : null}
          {activeKey === 'locations' ? (
            <Form.Item name="is_selectable" label="允许直接存放资产" valuePropName="checked">
              <Switch />
            </Form.Item>
          ) : null}
          {activeKey === 'categories' ? (
            <>
              <Form.Item
                name="service_life_months"
                label="标准使用期限（月）"
                rules={[{ required: true, message: '请输入标准使用期限' }]}
              >
                <InputNumber min={1} max={1200} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item
                name="default_unit_id"
                label="默认计量单位"
                rules={[{ required: true, message: '请选择默认计量单位' }]}
              >
                <Select
                  options={(query.data?.units ?? [])
                    .filter((item) => isEnabled(item.status))
                    .map((item) => ({ value: item.id, label: `${item.name}（${item.code}）` }))}
                />
              </Form.Item>
            </>
          ) : null}
          {activeKey === 'suppliers' ? (
            <>
              <Form.Item name="unified_social_credit_code" label="统一社会信用代码">
                <Input maxLength={64} />
              </Form.Item>
              <div className="operations-form-grid">
                <Form.Item name="contact_name" label="联系人">
                  <Input maxLength={128} />
                </Form.Item>
                <Form.Item name="contact_phone" label="联系电话">
                  <Input maxLength={64} />
                </Form.Item>
              </div>
              <Form.Item name="address" label="地址">
                <Input maxLength={500} />
              </Form.Item>
              <Form.Item name="remark" label="备注">
                <Input.TextArea rows={3} maxLength={1000} showCount />
              </Form.Item>
            </>
          ) : null}
          {activeKey === 'public-objects' ? (
            <p className="operations-form-note">
              对象编码由后端自动生成。已被引用的对象只能停用，历史关系会继续保留。
            </p>
          ) : null}
        </Form>
      </Modal>

      <Modal
        open={Boolean(deleteTarget)}
        title={`删除${deleteTarget?.kind === 'locations' ? '地点' : '资产分类'}“${deleteTarget?.node.name ?? ''}”`}
        okText="确认永久删除"
        cancelText="取消"
        okButtonProps={{
          danger: true,
          disabled: !deleteImpact?.can_delete || deleteReason.trim().length < 2,
        }}
        confirmLoading={deleteMutation.isPending}
        className="operations-glass-modal operations-impact-modal"
        onOk={() => deleteMutation.mutate()}
        onCancel={() => {
          setDeleteTarget(null)
          setDeleteImpact(null)
          setDeleteReason('')
        }}
      >
        {deleteImpactLoading ? (
          <div className="operations-loading">
            <Spin />
          </div>
        ) : deleteImpact ? (
          <div className="operations-delete-review">
            <p className="operations-form-note">
              编码 <strong>{deleteImpact.code}</strong>{' '}
              删除后不会复用。系统已检查当前业务和历史留痕。
            </p>
            <div className="operations-impact-grid">
              {deleteImpact.references.map((item) => (
                <div key={item.key} className="operations-impact-item">
                  <span>{item.label}</span>
                  <strong>{item.count}</strong>
                </div>
              ))}
            </div>
            {deleteImpact.blockers.length ? (
              <div className="operations-delete-blockers">
                <AlertTriangle size={18} />
                <div>
                  <strong>当前不能删除</strong>
                  {deleteImpact.blockers.map((item) => (
                    <span key={item}>{item}</span>
                  ))}
                </div>
              </div>
            ) : (
              <p className="operations-form-note">未发现下级节点、业务引用或历史引用，可以删除。</p>
            )}
            <label className="operations-delete-reason">
              <span>删除原因</span>
              <Input.TextArea
                rows={3}
                maxLength={500}
                showCount
                disabled={!deleteImpact.can_delete}
                value={deleteReason}
                placeholder="请说明为什么确认这是一个从未使用的错误资料"
                onChange={(event) => setDeleteReason(event.target.value)}
              />
            </label>
          </div>
        ) : null}
      </Modal>
    </div>
  )
}
