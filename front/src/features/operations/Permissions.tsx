import { Button, Input, Spin } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { Check, Search, ShieldCheck, UsersRound } from 'lucide-react'
import { useMemo, useState } from 'react'
import { administrationApi } from '@/api/administration'
import StatePanel from '@/components/ui/StatePanel'
import { useAuthStore } from '@/store/auth'
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
  CURRENT_ORG: '当前组织',
  CURRENT_AND_CHILDREN: '当前及下级组织',
  CUSTOM: '自定义组织范围',
  SELF: '仅本人数据',
}

const roleTones: Tone[] = ['violet', 'blue', 'cyan', 'amber', 'green', 'slate']

export default function Permissions() {
  const [keyword, setKeyword] = useState('')
  const permissions = useAuthStore((state) => state.user?.permissions ?? [])
  const canViewUsers = permissions.includes('system:user:view')
  const accessQuery = useQuery({
    queryKey: ['administration', 'roles-permissions'],
    queryFn: async () => {
      const [roles, permissionItems] = await Promise.all([
        administrationApi.roles(),
        administrationApi.permissions(),
      ])
      return { roles, permissionItems }
    },
  })
  const usersQuery = useQuery({
    queryKey: ['administration', 'users'],
    queryFn: () => administrationApi.users(0, 100),
    enabled: canViewUsers,
  })
  const roles = useMemo(() => accessQuery.data?.roles ?? [], [accessQuery.data?.roles])
  const permissionItems = useMemo(
    () => accessQuery.data?.permissionItems ?? [],
    [accessQuery.data?.permissionItems],
  )
  const modules = useMemo(
    () => Array.from(new Set(permissionItems.map((item) => item.module))).sort(),
    [permissionItems],
  )
  const roleNameByCode = useMemo(
    () => new Map(roles.map((role) => [role.code, role.name])),
    [roles],
  )
  const normalizedKeyword = keyword.trim().toLowerCase()
  const users = (usersQuery.data?.items ?? []).filter(
    (user) =>
      !normalizedKeyword ||
      [user.username, user.nickname ?? '', ...(user.roles ?? [])].some((value) =>
        value.toLowerCase().includes(normalizedKeyword),
      ),
  )
  const builtInCount = roles.filter((role) => role.built_in).length
  const enabledPermissionCount = permissionItems.filter((item) => item.enabled).length

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow="ACCESS CONTROL"
        title="权限只给需要的人，变化都留下记录"
        description="角色、权限点与用户授权信息已连接后端；当前页面先提供真实配置查询。"
        icon={ShieldCheck}
        tone="violet"
        actions={
          <Button type="primary" size="large" disabled>
            权限编辑待接入
          </Button>
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
            hint: '不可继续授权',
            tone: 'amber',
          },
        ]}
      />

      <GlassPanel>
        <SectionHeading
          eyebrow="ROLES"
          title="角色模板"
          description="角色能力与数据范围来自后端 RBAC 配置。"
          action={<StatusPill label="只读模式" tone="slate" />}
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
                    <StatusPill label={role.built_in ? '系统内置' : '自定义'} tone={tone} />
                  </div>
                  <h3>{role.name}</h3>
                  <p>
                    {role.code} · {scopeLabels[role.data_scope] ?? role.data_scope}
                  </p>
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
                      <strong>{role.enabled ? '启用' : '停用'}</strong>
                      <span>角色状态</span>
                    </div>
                  </div>
                </article>
              )
            })}
          </div>
        ) : (
          <StatePanel mode="empty" message="暂无角色配置" />
        )}
      </GlassPanel>

      <div className="operations-split">
        <GlassPanel>
          <SectionHeading
            eyebrow="MATRIX"
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
                        <td>{module}</td>
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
            eyebrow="USERS"
            title="授权用户"
            description={
              canViewUsers
                ? '显示后端返回的前 100 名用户。'
                : '当前账号没有 system:user:view 权限。'
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
                <div className="operations-task-list">
                  {users.map((user, index) => (
                    <div
                      key={user.id}
                      className={`operations-user-row operations-tone--${index % 2 ? 'cyan' : 'violet'}`}
                    >
                      <span className="operations-user-row__avatar">
                        {(user.nickname || user.username).slice(0, 1)}
                      </span>
                      <div className="operations-user-row__content">
                        <strong>{user.nickname || user.username}</strong>
                        <span>
                          {user.username} · 组织 #{user.organization_id ?? '未设置'}
                        </span>
                      </div>
                      <StatusPill
                        label={
                          (user.roles ?? [])
                            .map((code) => roleNameByCode.get(code) ?? code)
                            .join('、') || '未授权角色'
                        }
                        tone={user.enabled === false ? 'slate' : 'blue'}
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <StatePanel mode="empty" message="没有匹配的用户" />
              )}
              <Button block style={{ marginTop: 14 }} icon={<UsersRound size={16} />} disabled>
                当前展示前 100 名用户
              </Button>
            </>
          ) : (
            <StatePanel mode="empty" message="当前账号无权查看用户列表" />
          )}
        </GlassPanel>
      </div>
    </div>
  )
}
