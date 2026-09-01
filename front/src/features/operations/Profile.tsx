import { App, Button, Form, Input, Modal, Spin, Switch } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, Building2, KeyRound, Laptop, LogOut, ShieldCheck, UserRound } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { authApi } from '@/api'
import StatePanel from '@/components/ui/StatePanel'
import { useAuthStore } from '@/store/auth'
import { formatBeijingDateTime } from '@/utils/dateTime'
import { GlassPanel, OperationsHero, SectionHeading, StatusPill } from './OperationsUI'

interface PasswordFormValues {
  current_password: string
  new_password: string
  confirm_password: string
}

export default function Profile() {
  const { message, modal } = App.useApp()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()
  const { user, setAuth, setUser, logout } = useAuthStore()
  const requiredByQuery = searchParams.get('changePassword') === 'required'
  const [passwordOpen, setPasswordOpen] = useState(requiredByQuery)
  const [passwordForm] = Form.useForm<PasswordFormValues>()
  const query = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: async () => {
      const currentUser = await authApi.me()
      setUser(currentUser)
      return currentUser
    },
    initialData: user ?? undefined,
  })
  const preferenceQuery = useQuery({
    queryKey: ['auth', 'preferences'],
    queryFn: authApi.preferences,
  })
  const sessionQuery = useQuery({
    queryKey: ['auth', 'sessions'],
    queryFn: authApi.sessions,
  })
  const preferenceMutation = useMutation({
    mutationFn: authApi.updatePreferences,
    onSuccess: (preferences) => {
      queryClient.setQueryData(['auth', 'preferences'], preferences)
      void message.success('个人偏好已保存')
    },
    onError: (error) =>
      void message.error(error instanceof Error ? error.message : '个人偏好保存失败'),
  })
  const revokeSessionMutation = useMutation({
    mutationFn: authApi.revokeSession,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['auth', 'sessions'] })
      void message.success('其他设备会话已撤销')
    },
    onError: (error) => void message.error(error instanceof Error ? error.message : '会话撤销失败'),
  })
  const passwordMutation = useMutation({
    mutationFn: (values: PasswordFormValues) =>
      authApi.changePassword({
        current_password: values.current_password,
        new_password: values.new_password,
      }),
    onSuccess: (result) => {
      setAuth(result.token, result.user)
      setPasswordOpen(false)
      passwordForm.resetFields()
      void message.success('密码已更新，安全会话已重新签发')
      navigate('/home', { replace: true })
    },
    onError: (error) => void message.error(error instanceof Error ? error.message : '密码修改失败'),
  })
  const currentUser = query.data ?? user
  const displayName = currentUser?.nickname || currentUser?.username || '用户'
  const roles = currentUser?.roles ?? (currentUser?.role ? [currentUser.role] : [])
  const permissions = currentUser?.permissions ?? []
  const passwordChangeRequired = Boolean(requiredByQuery || currentUser?.must_change_password)

  useEffect(() => {
    if (passwordChangeRequired) setPasswordOpen(true)
  }, [passwordChangeRequired])

  const handleLogout = () => {
    void authApi.logout().finally(() => {
      logout()
      navigate('/login')
    })
  }

  const confirmPasswordChange = async () => {
    const values = await passwordForm.validateFields()
    if (passwordChangeRequired) {
      await passwordMutation.mutateAsync(values)
      return
    }
    modal.confirm({
      title: '确认修改登录密码？',
      content: '修改后会撤销其他旧会话，并为当前浏览器签发新的安全会话。',
      okText: '确认修改',
      cancelText: '返回检查',
      onOk: () => passwordMutation.mutateAsync(values),
    })
  }

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow="MY WORKSPACE"
        title={`你好，${displayName}`}
        description="账号、组织、角色和权限信息已连接后端；登录密码可以在此安全更新。"
        icon={UserRound}
        tone="blue"
        actions={
          <Button
            type="primary"
            size="large"
            icon={<KeyRound size={17} />}
            onClick={() => setPasswordOpen(true)}
          >
            修改登录密码
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
                eyebrow="PREFERENCES"
                title="消息与列表偏好"
                description="设置会保存到当前账号，并在其他浏览器登录后继续生效。"
                action={
                  preferenceMutation.isPending ? (
                    <Spin size="small" />
                  ) : (
                    <StatusPill label="账号同步" tone="green" />
                  )
                }
              />
              {preferenceQuery.isLoading ? (
                <div className="operations-loading">
                  <Spin />
                </div>
              ) : preferenceQuery.isError || !preferenceQuery.data ? (
                <StatePanel
                  mode="error"
                  message="个人偏好加载失败"
                  retryLabel="重新加载"
                  onRetry={() => void preferenceQuery.refetch()}
                />
              ) : (
                <div className="operations-settings-list">
                  <div className="operations-setting">
                    <span className="operations-setting__icon">
                      <Bell size={18} />
                    </span>
                    <div className="operations-setting__content">
                      <strong>资产任务提醒</strong>
                      <span>领用、退库和盘点任务更新时显示系统待办</span>
                    </div>
                    <Switch
                      checked={preferenceQuery.data.task_notice}
                      onChange={(task_notice) => preferenceMutation.mutate({ task_notice })}
                    />
                  </div>
                  <div className="operations-setting">
                    <span className="operations-setting__icon">
                      <ShieldCheck size={18} />
                    </span>
                    <div className="operations-setting__content">
                      <strong>审批待办提醒</strong>
                      <span>收到新的系统内审批任务时显示待办</span>
                    </div>
                    <Switch
                      checked={preferenceQuery.data.approval_notice}
                      onChange={(approval_notice) => preferenceMutation.mutate({ approval_notice })}
                    />
                  </div>
                  <div className="operations-setting">
                    <span className="operations-setting__icon">
                      <Bell size={18} />
                    </span>
                    <div className="operations-setting__content">
                      <strong>每周资产摘要</strong>
                      <span>保存摘要订阅偏好；正式发送仍需外部通知通道</span>
                    </div>
                    <Switch
                      checked={preferenceQuery.data.weekly_digest}
                      onChange={(weekly_digest) => preferenceMutation.mutate({ weekly_digest })}
                    />
                  </div>
                </div>
              )}
            </GlassPanel>

            <GlassPanel>
              <SectionHeading
                eyebrow="SESSIONS"
                title="登录设备"
                description="展示后端记录的当前和历史会话，可撤销其他仍有效的登录。"
                action={
                  <Button size="small" onClick={() => void sessionQuery.refetch()}>
                    刷新
                  </Button>
                }
              />
              {sessionQuery.isLoading ? (
                <div className="operations-loading">
                  <Spin />
                </div>
              ) : sessionQuery.isError ? (
                <StatePanel
                  mode="error"
                  message="登录会话加载失败"
                  retryLabel="重新加载"
                  onRetry={() => void sessionQuery.refetch()}
                />
              ) : (
                <div className="operations-settings-list">
                  {(sessionQuery.data ?? []).map((session) => (
                    <div
                      key={session.session_id}
                      className={`operations-setting${session.current ? ' operations-tone--green' : ''}`}
                    >
                      <span className="operations-setting__icon">
                        <Laptop size={18} />
                      </span>
                      <div className="operations-setting__content">
                        <strong>{session.current ? '当前浏览器' : '其他登录设备'}</strong>
                        <span>
                          {session.ip_address ?? '未知网络'} · 最近活动{' '}
                          {formatBeijingDateTime(session.last_seen_at)}
                        </span>
                        <small>{session.user_agent || '未记录浏览器信息'}</small>
                      </div>
                      {session.current ? (
                        <StatusPill label="当前" tone="green" />
                      ) : session.active ? (
                        <Button
                          danger
                          size="small"
                          loading={revokeSessionMutation.isPending}
                          onClick={() => revokeSessionMutation.mutate(session.session_id)}
                        >
                          撤销
                        </Button>
                      ) : (
                        <StatusPill label="已结束" tone="slate" />
                      )}
                    </div>
                  ))}
                </div>
              )}
            </GlassPanel>
          </div>
        </div>
      )}

      <Modal
        className="operations-glass-modal"
        title={passwordChangeRequired ? '首次登录，请设置新密码' : '修改登录密码'}
        open={passwordOpen}
        width={560}
        okText="更新密码"
        cancelText="取消"
        closable={!passwordChangeRequired}
        keyboard={!passwordChangeRequired}
        maskClosable={!passwordChangeRequired}
        cancelButtonProps={passwordChangeRequired ? { style: { display: 'none' } } : undefined}
        confirmLoading={passwordMutation.isPending}
        onOk={() => void confirmPasswordChange()}
        onCancel={() => {
          if (passwordChangeRequired) return
          setPasswordOpen(false)
          passwordForm.resetFields()
        }}
      >
        {passwordChangeRequired ? (
          <p className="operations-modal-note">
            为保护本地账号，首次登录必须修改初始密码。完成前只能访问个人资料和退出登录。
          </p>
        ) : null}
        <Form<PasswordFormValues> form={passwordForm} layout="vertical" requiredMark={false}>
          <Form.Item
            name="current_password"
            label="当前密码"
            rules={[{ required: true, message: '请输入当前密码' }]}
          >
            <Input.Password autoComplete="current-password" maxLength={128} />
          </Form.Item>
          <Form.Item
            name="new_password"
            label="新密码"
            extra="至少 12 位，并同时包含大写字母、小写字母、数字和特殊字符。"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 12, message: '新密码至少 12 位' },
              { pattern: /[a-z]/, message: '需要包含小写字母' },
              { pattern: /[A-Z]/, message: '需要包含大写字母' },
              { pattern: /[0-9]/, message: '需要包含数字' },
              { pattern: /[^A-Za-z0-9]/, message: '需要包含特殊字符' },
            ]}
          >
            <Input.Password autoComplete="new-password" maxLength={128} />
          </Form.Item>
          <Form.Item
            name="confirm_password"
            label="确认新密码"
            dependencies={['new_password']}
            rules={[
              { required: true, message: '请再次输入新密码' },
              ({ getFieldValue }) => ({
                validator: (_, value: string) =>
                  !value || value === getFieldValue('new_password')
                    ? Promise.resolve()
                    : Promise.reject(new Error('两次输入的新密码不一致')),
              }),
            ]}
          >
            <Input.Password autoComplete="new-password" maxLength={128} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
