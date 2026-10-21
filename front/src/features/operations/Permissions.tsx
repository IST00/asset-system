import {
  App,
  Button,
  Checkbox,
  Form,
  Input,
  Modal,
  Pagination,
  Radio,
  Select,
  Spin,
  Switch,
} from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  Check,
  Pencil,
  Plus,
  Search,
  ShieldCheck,
  Trash2,
  UserCog,
  UsersRound,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import {
  administrationApi,
  masterDataApi,
  type DeleteImpact,
  type PermissionItem,
  type RoleItem,
  type TreeItem,
} from '@/api/administration'
import StatePanel from '@/components/ui/StatePanel'
import { useAuthStore } from '@/store/auth'
import type { User } from '@/types'
import { dataScopeLabel } from '@/utils/displayLabels'
import type { Tone } from './data'
import {
  GlassPanel,
  OperationsHero,
  OperationsMetrics,
  SectionHeading,
  StatusPill,
} from './OperationsUI'

const scopeLabels: Record<string, string> = {
  ALL: '全部组织',
  DEPARTMENT: '当前组织',
  DEPARTMENT_TREE: '当前及下级组织',
  CUSTOM: '自定义组织范围',
  SELF: '仅本人数据',
}

const permissionModuleLabels: Record<string, string> = {
  approval: '审批管理',
  asset: '资产台账',
  'asset-category': '资产分类',
  'asset-lifecycle': '资产生命周期',
  'asset-source': '资产来源',
  audit: '审计日志',
  inventory: '资产盘点',
  location: '存放地点',
  'master-data': '基础资料',
  organization: '组织架构',
  'stock-in': '资产入库',
  supplier: '供应商',
  system: '系统权限',
  unit: '计量单位',
}

const permissionNameOverrides: Record<string, string> = {
  'approval:execution:terminate': '终止审批执行',
  'approval:flow:disable': '停用审批流程',
  'approval:flow:edit': '编辑审批流程',
  'approval:flow:publish': '发布审批流程',
  'approval:flow:view': '查看审批流程',
  'approval:task:approve': '审批待办任务',
  'approval:task:view': '查看审批任务',
  'operation:request:view': '查看业务申请',
}

function permissionModuleLabel(module: string): string {
  return permissionModuleLabels[module] ?? '其他权限模块'
}

function permissionDisplayName(item: PermissionItem): string {
  const override = permissionNameOverrides[item.code]
  if (override) return override
  return /[\u3400-\u9fff]/u.test(item.name) ? item.name : '其他权限操作'
}

const scopeOptions = Object.entries(scopeLabels).map(([value, label]) => ({ value, label }))
const roleTones: Tone[] = ['violet', 'blue', 'cyan', 'amber', 'green', 'slate']
const userDisplayRolePriority: Record<string, number> = {
  SUPER_ADMIN: 0,
  ASSET_ADMIN: 1,
  USER: 2,
}

function roleDisplayPriority(code: string): number {
  return userDisplayRolePriority[code] ?? Object.keys(userDisplayRolePriority).length
}

type RoleDialogMode = 'create' | 'basic' | 'permissions'

interface RoleFormValues {
  code?: string
  name: string
  data_scope: string
  enabled: boolean
  organization_ids?: number[]
  permission_ids?: number[]
  reason: string
}

interface UserRoleFormValues {
  role_id: number
  reason: string
}

function flattenOrganizations(items: TreeItem[], depth = 0): { value: number; label: string }[] {
  return items.flatMap((item) => [
    { value: item.id, label: `${'　'.repeat(depth)}${item.name}（${item.code}）` },
    ...flattenOrganizations(item.children ?? [], depth + 1),
  ])
}

export default function Permissions() {
  const { message, modal } = App.useApp()
  const [keyword, setKeyword] = useState('')
  const [userPage, setUserPage] = useState(0)
  const [debouncedKeyword, setDebouncedKeyword] = useState('')
  const [roleDialog, setRoleDialog] = useState<RoleDialogMode | null>(null)
  const [editingRole, setEditingRole] = useState<RoleItem | null>(null)
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [deleteRole, setDeleteRole] = useState<RoleItem | null>(null)
  const [deleteImpact, setDeleteImpact] = useState<DeleteImpact | null>(null)
  const [deleteReason, setDeleteReason] = useState('')
  const [deleteImpactLoading, setDeleteImpactLoading] = useState(false)
  const [roleForm] = Form.useForm<RoleFormValues>()
  const [userRoleForm] = Form.useForm<UserRoleFormValues>()
  const queryClient = useQueryClient()
  const currentUser = useAuthStore((state) => state.user)
  const permissions = useMemo(
    () => new Set(currentUser?.permissions ?? []),
    [currentUser?.permissions],
  )
  const currentRoleCodes = useMemo(() => new Set(currentUser?.roles ?? []), [currentUser?.roles])
  const canViewUsers = permissions.has('system:user:view')
  const canManage = permissions.has('system:role:manage')

  const isCurrentSuperAdmin = currentRoleCodes.has('SUPER_ADMIN')

  const canConfigureRole = (role: RoleItem) => isCurrentSuperAdmin || role.code !== 'SUPER_ADMIN'

  const canAssignUserRole = (user: User) =>
    isCurrentSuperAdmin || !(user.roles ?? []).includes('SUPER_ADMIN')

  const accessQuery = useQuery({
    queryKey: ['administration', 'roles-permissions'],
    queryFn: async () => {
      const [roles, permissionItems, organizations] = await Promise.all([
        administrationApi.roles(),
        administrationApi.permissions(),
        masterDataApi.organizations(),
      ])
      return { roles, permissionItems, organizations }
    },
  })
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedKeyword(keyword.trim())
      setUserPage(0)
    }, 300)
    return () => window.clearTimeout(timer)
  }, [keyword])

  const usersQuery = useQuery({
    queryKey: ['administration', 'users', userPage, debouncedKeyword],
    queryFn: () => administrationApi.users(userPage, 50, debouncedKeyword),
    enabled: canViewUsers,
    placeholderData: (previous) => previous,
  })
  const roles = useMemo(() => accessQuery.data?.roles ?? [], [accessQuery.data?.roles])
  const permissionItems = useMemo(
    () => accessQuery.data?.permissionItems ?? [],
    [accessQuery.data?.permissionItems],
  )
  const modules = useMemo(
    () =>
      Array.from(new Set(permissionItems.map((item) => item.module))).sort((left, right) =>
        permissionModuleLabel(left).localeCompare(permissionModuleLabel(right), 'zh-CN'),
      ),
    [permissionItems],
  )
  const organizationOptions = useMemo(
    () => flattenOrganizations(accessQuery.data?.organizations ?? []),
    [accessQuery.data?.organizations],
  )
  const roleIdByCode = useMemo(() => new Map(roles.map((role) => [role.code, role.id])), [roles])
  const users = (usersQuery.data?.items ?? [])
    .map((user) => ({
      user,
      rolePriority: Math.min(...(user.roles ?? []).map(roleDisplayPriority)),
    }))
    .sort((left, right) =>
      left.rolePriority !== right.rolePriority
        ? left.rolePriority - right.rolePriority
        : left.user.username.localeCompare(right.user.username, 'zh-CN') ||
          (left.user.nickname ?? '').localeCompare(right.user.nickname ?? '', 'zh-CN'),
    )
    .map(({ user }) => user)
  const builtInCount = roles.filter((role) => role.built_in).length
  const enabledPermissionCount = permissionItems.filter((item) => item.enabled).length

  const refreshAccess = async () => {
    await queryClient.invalidateQueries({ queryKey: ['administration', 'roles-permissions'] })
    await queryClient.invalidateQueries({ queryKey: ['administration', 'users'] })
    await queryClient.invalidateQueries({ queryKey: ['audit-logs'] })
  }

  const roleMutation = useMutation({
    mutationFn: async (values: RoleFormValues) => {
      if (roleDialog === 'create') {
        return administrationApi.createRole({
          code: values.code?.trim() ?? '',
          name: values.name.trim(),
          data_scope: values.data_scope,
          reason: values.reason.trim(),
        })
      }
      if (!editingRole) throw new Error('请选择要编辑的角色')
      if (roleDialog === 'permissions') {
        return administrationApi.updateRolePermissions(
          editingRole.id,
          values.permission_ids ?? [],
          values.reason.trim(),
        )
      }
      return administrationApi.updateRole(editingRole.id, {
        name: values.name.trim(),
        data_scope: values.data_scope,
        enabled: values.enabled,
        organization_ids: values.data_scope === 'CUSTOM' ? (values.organization_ids ?? []) : [],
        version: editingRole.version,
        reason: values.reason.trim(),
      })
    },
    onSuccess: async () => {
      setRoleDialog(null)
      setEditingRole(null)
      roleForm.resetFields()
      await refreshAccess()
      void message.success('角色配置已保存并记录操作日志')
    },
    onError: (error) =>
      void message.error(error instanceof Error ? error.message : '角色配置保存失败'),
  })

  const userRoleMutation = useMutation({
    mutationFn: (values: UserRoleFormValues) => {
      if (!editingUser) throw new Error('请选择要授权的用户')
      return administrationApi.updateUserRoles(
        editingUser.id,
        [values.role_id],
        values.reason.trim(),
      )
    },
    onSuccess: async () => {
      setEditingUser(null)
      userRoleForm.resetFields()
      await refreshAccess()
      void message.success('用户角色已更新并记录操作日志')
    },
    onError: (error) => void message.error(error instanceof Error ? error.message : '用户授权失败'),
  })

  const deleteRoleMutation = useMutation({
    mutationFn: async () => {
      if (!deleteRole || !deleteImpact) throw new Error('请先检查角色删除影响')
      return administrationApi.deleteRole(deleteRole.id, {
        version: deleteImpact.version,
        reason: deleteReason.trim(),
        confirmed: true,
      })
    },
    onSuccess: async () => {
      setDeleteRole(null)
      setDeleteImpact(null)
      setDeleteReason('')
      await refreshAccess()
      void message.success('角色已删除并记录永久审计日志')
    },
    onError: (error) => void message.error(error instanceof Error ? error.message : '角色删除失败'),
  })

  const openDeleteRole = async (role: RoleItem) => {
    setDeleteRole(role)
    setDeleteImpact(null)
    setDeleteReason('')
    setDeleteImpactLoading(true)
    try {
      setDeleteImpact(await administrationApi.roleDeleteImpact(role.id))
    } catch (error) {
      setDeleteRole(null)
      void message.error(error instanceof Error ? error.message : '角色删除影响检查失败')
    } finally {
      setDeleteImpactLoading(false)
    }
  }

  const openCreateRole = () => {
    setEditingRole(null)
    setRoleDialog('create')
    roleForm.setFieldsValue({
      code: '',
      name: '',
      data_scope: 'SELF',
      enabled: true,
      organization_ids: [],
      reason: '',
    })
  }

  const openRoleEditor = (role: RoleItem, mode: Exclude<RoleDialogMode, 'create'>) => {
    setEditingRole(role)
    setRoleDialog(mode)
    roleForm.setFieldsValue({
      name: role.name,
      data_scope: role.data_scope,
      enabled: role.enabled,
      organization_ids: role.organization_ids,
      permission_ids: permissionItems
        .filter((item) => role.permissions.includes(item.code))
        .map((item) => item.id),
      reason: '',
    })
  }

  const openUserRoles = (user: User) => {
    setEditingUser(user)
    const roleIds = (user.roles ?? [])
      .map((code) => roleIdByCode.get(code))
      .filter((id): id is number => id !== undefined)
    userRoleForm.setFieldsValue({
      role_id: roleIds[0],
      reason: '',
    })
  }

  const confirmRoleSave = async () => {
    const values = await roleForm.validateFields()
    modal.confirm({
      title: roleDialog === 'create' ? '确认创建角色？' : '确认保存权限变更？',
      content: '保存后会立即影响后续鉴权；已登录用户需重新登录才能刷新前端权限菜单。',
      okText: '确认保存',
      cancelText: '返回检查',
      onOk: () => roleMutation.mutateAsync(values),
    })
  }

  const confirmUserRoleSave = async () => {
    const values = await userRoleForm.validateFields()
    modal.confirm({
      title: '确认更新用户角色？',
      content: '每个账号只能保留一个角色；新角色会替换该用户当前角色，请确认后保存。',
      okText: '确认授权',
      cancelText: '返回检查',
      onOk: () => userRoleMutation.mutateAsync(values),
    })
  }

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow="权限控制"
        title="权限只给需要的人，每次变化都有理由"
        description="角色、权限点、组织数据范围与用户授权均连接后端；敏感修改需要填写原因并二次确认。"
        icon={ShieldCheck}
        tone="violet"
        actions={
          canManage ? (
            <Button type="primary" size="large" icon={<Plus size={18} />} onClick={openCreateRole}>
              新建角色
            </Button>
          ) : null
        }
        aside={
          <div className="operations-hero__aside-card">
            <span>受管用户</span>
            <strong>{canViewUsers ? (usersQuery.data?.total ?? 0) : '—'}</strong>
            <small>{canViewUsers ? '来自后端用户接口' : '当前账号无用户查看权限'}</small>
          </div>
        }
      />

      <OperationsMetrics
        items={[
          {
            label: '系统角色',
            value: roles.length,
            hint: `${builtInCount} 个系统内置角色`,
            tone: 'violet',
          },
          {
            label: '已授权用户',
            value: canViewUsers ? (usersQuery.data?.total ?? 0) : '—',
            hint: canViewUsers ? '当前后端用户总数' : '无查看权限',
            tone: 'blue',
          },
          {
            label: '启用权限点',
            value: enabledPermissionCount,
            hint: `覆盖 ${modules.length} 个模块`,
            tone: 'cyan',
          },
          {
            label: '停用角色',
            value: roles.filter((role) => !role.enabled).length,
            hint: '停用后不再授予权限',
            tone: 'amber',
          },
        ]}
      />

      <GlassPanel>
        <SectionHeading
          eyebrow="角色配置"
          title="角色与数据范围"
          description="角色编码创建后不可修改；内置角色不会在本页提供删除入口。"
          action={
            <StatusPill
              label={canManage ? '可管理' : '只读'}
              tone={canManage ? 'violet' : 'slate'}
            />
          }
        />
        {accessQuery.isLoading ? (
          <div className="operations-loading">
            <Spin />
          </div>
        ) : accessQuery.isError ? (
          <StatePanel
            mode="error"
            message="角色与权限加载失败"
            retryLabel="重新加载"
            onRetry={() => void accessQuery.refetch()}
          />
        ) : roles.length ? (
          <div className="operations-grid operations-grid--two">
            {roles.map((role, index) => {
              const tone = roleTones[index % roleTones.length]
              return (
                <article
                  key={role.id}
                  className={`operations-card operations-role-card operations-tone--${tone}`}
                >
                  <div className="operations-role-card__top">
                    <span className="operations-card__icon">
                      <ShieldCheck size={21} />
                    </span>
                    <div className="operations-role-card__badges">
                      <StatusPill label={role.built_in ? '系统内置' : '自定义'} tone={tone} />
                      {!role.enabled ? <StatusPill label="已停用" tone="slate" /> : null}
                    </div>
                  </div>
                  <h3>{role.name}</h3>
                  <p>{dataScopeLabel(role.data_scope)}</p>
                  <div className="operations-role-card__counts">
                    <div>
                      <strong>{role.organization_ids.length || '—'}</strong>
                      <span>自定义组织</span>
                    </div>
                    <div>
                      <strong>{role.permissions.length}</strong>
                      <span>权限点</span>
                    </div>
                    <div>
                      <strong>v{role.version}</strong>
                      <span>配置版本</span>
                    </div>
                  </div>
                  {canManage ? (
                    <div className="operations-role-card__actions">
                      {canConfigureRole(role) ? (
                        <>
                          <Button
                            icon={<Pencil size={15} />}
                            onClick={() => openRoleEditor(role, 'basic')}
                          >
                            编辑角色
                          </Button>
                          <Button
                            icon={<ShieldCheck size={15} />}
                            onClick={() => openRoleEditor(role, 'permissions')}
                          >
                            配置权限点
                          </Button>
                        </>
                      ) : null}
                      {!role.built_in ? (
                        <Button
                          danger
                          icon={<Trash2 size={15} />}
                          onClick={() => void openDeleteRole(role)}
                        >
                          删除角色
                        </Button>
                      ) : null}
                    </div>
                  ) : null}
                </article>
              )
            })}
          </div>
        ) : (
          <StatePanel mode="empty" message="暂无角色配置" />
        )}
      </GlassPanel>

      <GlassPanel>
        <SectionHeading
          eyebrow="权限矩阵"
          title="权限覆盖矩阵"
          description="根据角色拥有的权限码，按后端模块实时汇总。"
        />
        {roles.length && modules.length ? (
          <div className="operations-permission-matrix">
            <table>
              <thead>
                <tr>
                  <th>权限模块</th>
                  {roles.map((role) => (
                    <th key={role.id}>{role.name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {modules.map((module) => {
                  const moduleCodes = permissionItems
                    .filter((item) => item.module === module && item.enabled)
                    .map((item) => item.code)
                  return (
                    <tr key={module}>
                      <td>{permissionModuleLabel(module)}</td>
                      {roles.map((role) => (
                        <td key={`${module}-${role.id}`}>
                          {moduleCodes.some((code) => role.permissions.includes(code)) ? (
                            <span className="operations-permission-dot">
                              <Check size={13} />
                            </span>
                          ) : (
                            '—'
                          )}
                        </td>
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <StatePanel mode="empty" message="暂无权限矩阵数据" />
        )}
      </GlassPanel>

      <GlassPanel>
        <SectionHeading
          eyebrow="用户授权"
          title="授权用户"
          description={
            canViewUsers
              ? '按超级管理员、资产管理员、普通员工优先展示用户角色与数据范围。'
              : '当前账号没有用户查看权限。'
          }
        />
        {canViewUsers ? (
          <>
            <div className="operations-toolbar">
              <Input
                value={keyword}
                prefix={<Search size={15} />}
                allowClear
                placeholder="搜索用户、账号或角色"
                onChange={(event) => setKeyword(event.target.value)}
              />
            </div>
            {usersQuery.isLoading ? (
              <div className="operations-loading">
                <Spin />
              </div>
            ) : usersQuery.isError ? (
              <StatePanel
                mode="error"
                message="用户列表加载失败"
                retryLabel="重新加载"
                onRetry={() => void usersQuery.refetch()}
              />
            ) : users.length ? (
              <div className="operations-user-list">
                {users.map((user, index) => {
                  const userRoles = [...(user.roles ?? [])].sort(
                    (left, right) => roleDisplayPriority(left) - roleDisplayPriority(right),
                  )

                  return (
                    <article
                      key={user.id}
                      className={`operations-user-card operations-tone--${index % 2 ? 'cyan' : 'violet'}`}
                    >
                      <div className="operations-user-card__main">
                        <span className="operations-user-row__avatar">
                          {(user.nickname || user.username).slice(0, 1)}
                        </span>
                        <div className="operations-user-row__content">
                          <strong>{user.nickname || user.username}</strong>
                          <span>
                            {user.username} · {user.organization_path || '未设置组织'}
                          </span>
                        </div>
                        {user.enabled === false ? (
                          <StatusPill label="账号已停用" tone="slate" />
                        ) : null}
                        {canManage && canAssignUserRole(user) ? (
                          <Button icon={<UserCog size={15} />} onClick={() => openUserRoles(user)}>
                            分配角色
                          </Button>
                        ) : null}
                        {canManage && !canAssignUserRole(user) ? (
                          <StatusPill label="仅超级管理员可调整" tone="slate" />
                        ) : null}
                      </div>

                      <div className="operations-user-card__access">
                        <div className="operations-user-card__roles">
                          <small>角色</small>
                          <div className="operations-user-card__tags">
                            {userRoles.length ? (
                              <>
                                {userRoles.map((code) => {
                                  const role = roles.find((item) => item.code === code)
                                  return (
                                    <StatusPill
                                      key={code}
                                      label={
                                        role
                                          ? `${role.name} · ${dataScopeLabel(role.data_scope)}`
                                          : code
                                      }
                                      tone="blue"
                                    />
                                  )
                                })}
                                {user.enabled === false ? (
                                  <StatusPill label="权限不生效" tone="slate" />
                                ) : null}
                              </>
                            ) : (
                              <StatusPill label="未授权角色" tone="slate" />
                            )}
                          </div>
                        </div>
                      </div>
                    </article>
                  )
                })}
              </div>
            ) : (
              <StatePanel mode="empty" message="没有匹配的用户" />
            )}
            <div className="operations-user-pagination">
              <Pagination
                current={userPage + 1}
                pageSize={50}
                total={usersQuery.data?.total ?? 0}
                showSizeChanger={false}
                showTotal={(total) => `共 ${total} 名用户`}
                onChange={(page) => setUserPage(page - 1)}
              />
            </div>
            <div className="operations-form-note">
              <UsersRound size={15} /> 支持按账号、姓名服务端搜索；角色分配后列表会自动刷新。
            </div>
          </>
        ) : (
          <StatePanel mode="empty" message="当前账号无权查看用户列表" />
        )}
      </GlassPanel>

      <Modal
        className="operations-glass-modal"
        title={
          roleDialog === 'create'
            ? '新建角色'
            : roleDialog === 'permissions'
              ? `配置 ${editingRole?.name ?? ''} 的权限点`
              : `编辑 ${editingRole?.name ?? ''}`
        }
        open={roleDialog !== null}
        width={roleDialog === 'permissions' ? 760 : 620}
        okText="保存变化"
        cancelText="取消"
        confirmLoading={roleMutation.isPending}
        onOk={() => void confirmRoleSave()}
        onCancel={() => {
          setRoleDialog(null)
          setEditingRole(null)
          roleForm.resetFields()
        }}
      >
        <Form<RoleFormValues>
          form={roleForm}
          layout="vertical"
          requiredMark={false}
          className="operations-form-grid"
        >
          {roleDialog === 'create' ? (
            <Form.Item
              name="code"
              label="角色编码"
              rules={[
                { required: true, message: '请输入角色编码' },
                {
                  pattern: /^[A-Za-z][A-Za-z0-9_:-]*$/,
                  message: '请使用字母、数字、下划线、冒号或短横线',
                },
              ]}
            >
              <Input placeholder="请输入系统使用的角色标识" maxLength={64} />
            </Form.Item>
          ) : null}
          {roleDialog !== 'permissions' ? (
            <>
              <Form.Item
                name="name"
                label="角色名称"
                rules={[{ required: true, message: '请输入角色名称' }]}
              >
                <Input maxLength={128} />
              </Form.Item>
              <Form.Item
                name="data_scope"
                label="数据范围"
                rules={[{ required: true, message: '请选择数据范围' }]}
              >
                <Select options={scopeOptions} />
              </Form.Item>
              <Form.Item
                noStyle
                shouldUpdate={(previous, current) => previous.data_scope !== current.data_scope}
              >
                {({ getFieldValue }) =>
                  getFieldValue('data_scope') === 'CUSTOM' ? (
                    <Form.Item
                      name="organization_ids"
                      label="自定义组织"
                      rules={[{ required: true, message: '至少选择一个组织' }]}
                      className="operations-form-grid__wide"
                    >
                      <Select
                        mode="multiple"
                        showSearch
                        optionFilterProp="label"
                        options={organizationOptions}
                        placeholder="选择可访问组织"
                        maxTagCount="responsive"
                      />
                    </Form.Item>
                  ) : null
                }
              </Form.Item>
              {roleDialog === 'basic' ? (
                <Form.Item name="enabled" label="角色状态" valuePropName="checked">
                  <Switch checkedChildren="启用" unCheckedChildren="停用" />
                </Form.Item>
              ) : null}
            </>
          ) : (
            <Form.Item name="permission_ids" label="权限点" className="operations-form-grid__wide">
              <Checkbox.Group className="operations-permission-picker">
                {modules.map((module) => (
                  <section key={module}>
                    <strong>{permissionModuleLabel(module)}</strong>
                    <div>
                      {permissionItems
                        .filter((item) => item.module === module && item.enabled)
                        .map((item) => (
                          <Checkbox key={item.id} value={item.id}>
                            {permissionDisplayName(item)}
                          </Checkbox>
                        ))}
                    </div>
                  </section>
                ))}
              </Checkbox.Group>
            </Form.Item>
          )}
          <Form.Item
            name="reason"
            label="变更原因"
            rules={[
              { required: true, message: '请填写变更原因' },
              { min: 2, message: '变更原因至少 2 个字符' },
            ]}
            className="operations-form-grid__wide"
          >
            <Input.TextArea
              rows={3}
              maxLength={500}
              showCount
              placeholder="说明授权依据、工单或调整原因"
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        className="operations-glass-modal"
        title={`为 ${editingUser?.nickname || editingUser?.username || ''} 分配角色`}
        open={editingUser !== null}
        width={620}
        okText="确认授权"
        cancelText="取消"
        confirmLoading={userRoleMutation.isPending}
        onOk={() => void confirmUserRoleSave()}
        onCancel={() => {
          setEditingUser(null)
          userRoleForm.resetFields()
        }}
      >
        <Form<UserRoleFormValues> form={userRoleForm} layout="vertical" requiredMark={false}>
          <Form.Item
            name="role_id"
            label="账号角色（单选）"
            rules={[{ required: true, message: '请选择一个角色' }]}
            extra="权限向下包含：超级管理员包含资产管理员和普通员工，资产管理员包含普通员工。"
          >
            <Radio.Group className="operations-role-picker">
              {roles
                .filter(
                  (role) => role.enabled && (isCurrentSuperAdmin || role.code !== 'SUPER_ADMIN'),
                )
                .sort(
                  (left, right) => roleDisplayPriority(left.code) - roleDisplayPriority(right.code),
                )
                .map((role) => (
                  <Radio key={role.id} value={role.id}>
                    <strong>{role.name}</strong>
                    <small>{dataScopeLabel(role.data_scope)}</small>
                  </Radio>
                ))}
            </Radio.Group>
          </Form.Item>
          <Form.Item
            name="reason"
            label="变更原因"
            rules={[
              { required: true, message: '请填写变更原因' },
              { min: 2, message: '变更原因至少 2 个字符' },
            ]}
          >
            <Input.TextArea
              rows={3}
              maxLength={500}
              showCount
              placeholder="说明授权依据、工单或人员职责变化"
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={Boolean(deleteRole)}
        title={`删除角色“${deleteRole?.name ?? ''}”`}
        okText="确认永久删除"
        cancelText="取消"
        okButtonProps={{
          danger: true,
          disabled: !deleteImpact?.can_delete || deleteReason.trim().length < 2,
        }}
        confirmLoading={deleteRoleMutation.isPending}
        className="operations-glass-modal operations-impact-modal"
        onOk={() => deleteRoleMutation.mutate()}
        onCancel={() => {
          setDeleteRole(null)
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
              系统已检查用户授权和审批流程引用；删除会同时移除权限点与自定义组织范围。
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
              <p className="operations-form-note">当前角色没有用户或审批规则引用，可以删除。</p>
            )}
            <label className="operations-delete-reason">
              <span>删除原因</span>
              <Input.TextArea
                rows={3}
                maxLength={500}
                showCount
                disabled={!deleteImpact.can_delete}
                value={deleteReason}
                placeholder="请填写角色删除原因"
                onChange={(event) => setDeleteReason(event.target.value)}
              />
            </label>
          </div>
        ) : null}
      </Modal>
    </div>
  )
}
