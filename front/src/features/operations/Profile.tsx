import { Button, Spin, Switch } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { Bell, Building2, KeyRound, Laptop, LogOut, ShieldCheck, UserRound } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '@/api'
import StatePanel from '@/components/ui/StatePanel'
import { useAuthStore } from '@/store/auth'
import { GlassPanel, OperationsHero, SectionHeading, StatusPill } from './OperationsUI'

export default function Profile() {
  const navigate = useNavigate()
  const { user, setUser, logout } = useAuthStore()
  const [taskNotice, setTaskNotice] = useState(true)
  const [approvalNotice, setApprovalNotice] = useState(true)
  const [weeklyDigest, setWeeklyDigest] = useState(false)
  const query = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: async () => {
      const currentUser = await authApi.me()
      setUser(currentUser)
      return currentUser
    },
    initialData: user ?? undefined,
  })
  const currentUser = query.data ?? user
  const displayName = currentUser?.nickname || currentUser?.username || '用户'
  const roles = currentUser?.roles ?? (currentUser?.role ? [currentUser.role] : [])
  const permissions = currentUser?.permissions ?? []

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow="MY WORKSPACE"
        title={`你好，${displayName}`}
        description="账号、组织、角色和权限信息已连接后端；消息开关仅保存在当前页面，暂未同步到服务器。"
        icon={UserRound}
        tone="blue"
        actions={
          <Button type="primary" size="large" icon={<KeyRound size={17} />} disabled>
            安全设置接口暂未开放
          </Button>
        }
        aside={
          <div className="operations-hero__aside-card">
            <span>账号状态</span>
            <strong>{currentUser?.enabled === false ? '已停用' : '正常'}</strong>
            <small>来自当前用户接口</small>
          </div>
        }
      />

      {query.isLoading && !currentUser ? (
        <div className="operations-loading">
          <Spin />
        </div>
      ) : query.isError && !currentUser ? (
        <StatePanel
          mode="error"
          message="个人资料加载失败"
          retryLabel="重新加载"
          onRetry={() => void query.refetch()}
        />
      ) : (
        <div className="operations-profile-grid">
          <section className="operations-profile-card">
            <div className="operations-profile-card__identity">
              <div className="operations-profile-card__avatar">{displayName.slice(0, 1)}</div>
              <h2>{displayName}</h2>
              <p>@{currentUser?.username ?? '—'}</p>
              <div className="operations-profile-card__tags">
                <StatusPill label={roles[0] ?? '未分配角色'} tone="violet" />
                <StatusPill
                  label={currentUser?.enabled === false ? '账号停用' : '账号正常'}
                  tone={currentUser?.enabled === false ? 'slate' : 'green'}
                />
              </div>
            </div>
            <div className="operations-profile-card__details">
              <div className="operations-profile-card__detail">
                <span>用户编号</span>
                <strong>#{currentUser?.id ?? '—'}</strong>
              </div>
              <div className="operations-profile-card__detail">
                <span>组织编号</span>
                <strong>
                  {currentUser?.organization_id ? `#${currentUser.organization_id}` : '未设置'}
                </strong>
              </div>
              <div className="operations-profile-card__detail">
                <span>角色数量</span>
                <strong>{roles.length}</strong>
              </div>
              <div className="operations-profile-card__detail">
                <span>权限点数量</span>
                <strong>{permissions.length}</strong>
              </div>
            </div>
            <Button
              danger
              block
              style={{ marginTop: 22 }}
              icon={<LogOut size={16} />}
              onClick={handleLogout}
            >
              退出登录
            </Button>
          </section>

          <div className="operations-page" style={{ paddingBottom: 0 }}>
            <GlassPanel>
              <SectionHeading
                eyebrow="PROFILE"
                title="账号与授权"
                description="以下信息来自 /users/me，页面不再填充虚构邮箱或工作地点。"
                action={
                  query.isFetching ? (
                    <Spin size="small" />
                  ) : (
                    <StatusPill label="已连接后端" tone="green" />
                  )
                }
              />
              <div className="operations-grid operations-grid--two">
                <div className="operations-setting">
                  <span className="operations-setting__icon">
                    <Building2 size={18} />
                  </span>
                  <div className="operations-setting__content">
                    <strong>组织归属</strong>
                    <span>
                      {currentUser?.organization_id
                        ? `组织 #${currentUser.organization_id}`
                        : '后端未设置组织'}
                    </span>
                  </div>
                </div>
                <div className="operations-setting">
                  <span className="operations-setting__icon">
                    <ShieldCheck size={18} />
                  </span>
                  <div className="operations-setting__content">
                    <strong>系统角色</strong>
                    <span>{roles.join('、') || '未分配角色'}</span>
                  </div>
                </div>
                <div className="operations-setting">
                  <span className="operations-setting__icon">
                    <KeyRound size={18} />
                  </span>
                  <div className="operations-setting__content">
                    <strong>权限范围</strong>
                    <span>
                      {permissions.length ? `${permissions.length} 个后端权限点` : '当前没有权限点'}
                    </span>
                  </div>
                </div>
                <div className="operations-setting">
                  <span className="operations-setting__icon">
                    <UserRound size={18} />
                  </span>
                  <div className="operations-setting__content">
                    <strong>登录账号</strong>
                    <span>{currentUser?.username ?? '—'}</span>
                  </div>
                </div>
              </div>
            </GlassPanel>

            <GlassPanel>
              <SectionHeading
                eyebrow="LOCAL PREFERENCES"
                title="本地消息偏好"
                description="这些开关当前只影响本页面展示，后端尚无消息偏好保存接口。"
                action={<StatusPill label="本地设置" tone="amber" />}
              />
              <div className="operations-settings-list">
                <div className="operations-setting">
                  <span className="operations-setting__icon">
                    <Bell size={18} />
                  </span>
                  <div className="operations-setting__content">
                    <strong>资产任务提醒</strong>
                    <span>领用确认、退库和盘点任务更新时提醒</span>
                  </div>
                  <Switch checked={taskNotice} onChange={setTaskNotice} />
                </div>
                <div className="operations-setting">
                  <span className="operations-setting__icon">
                    <ShieldCheck size={18} />
                  </span>
                  <div className="operations-setting__content">
                    <strong>审批待办提醒</strong>
                    <span>收到新审批任务时提醒</span>
                  </div>
                  <Switch checked={approvalNotice} onChange={setApprovalNotice} />
                </div>
                <div className="operations-setting">
                  <span className="operations-setting__icon">
                    <Bell size={18} />
                  </span>
                  <div className="operations-setting__content">
                    <strong>每周资产摘要</strong>
                    <span>后端接口建设完成后可同步保存</span>
                  </div>
                  <Switch checked={weeklyDigest} onChange={setWeeklyDigest} />
                </div>
              </div>
            </GlassPanel>

            <GlassPanel>
              <SectionHeading
                eyebrow="SESSION"
                title="当前登录会话"
                description="后端暂未提供设备会话列表，因此仅显示当前浏览器会话。"
              />
              <div className="operations-settings-list">
                <div className="operations-setting operations-tone--green">
                  <span className="operations-setting__icon">
                    <Laptop size={18} />
                  </span>
                  <div className="operations-setting__content">
                    <strong>当前浏览器</strong>
                    <span>已使用后端 JWT 登录 · 退出登录会清除本地会话</span>
                  </div>
                  <StatusPill label="当前" tone="green" />
                </div>
              </div>
            </GlassPanel>
          </div>
        </div>
      )}
    </div>
  )
}
