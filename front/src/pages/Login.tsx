import { App, Button, Form, Input } from 'antd'
import {
  ArrowRight,
  Boxes,
  Building2,
  CheckCircle2,
  Fingerprint,
  LockKeyhole,
  ScanLine,
  ShieldCheck,
  Sparkles,
  UserRound,
} from 'lucide-react'
import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { authApi } from '@/api'
import {
  demoCredentials,
  demoToken,
  demoUser,
  isDemoCredentials,
  isDemoLoginEnabled,
} from '@/features/auth/demoAuth'
import { useAuthStore } from '@/store/auth'
import './Login.css'

interface LoginValues {
  username: string
  password: string
}

interface LoginLocationState {
  from?: {
    pathname?: string
  }
}

const capabilityItems = [
  { icon: Boxes, label: '资产全生命周期管理' },
  { icon: ScanLine, label: '移动盘点与标签追踪' },
  { icon: ShieldCheck, label: '角色权限与审批留痕' },
]

export default function Login() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const location = useLocation()
  const setAuth = useAuthStore((state) => state.setAuth)
  const [loading, setLoading] = useState(false)
  const demoEnabled =
    import.meta.env.DEV && isDemoLoginEnabled(import.meta.env.VITE_ENABLE_DEMO_LOGIN)
  const from = (location.state as LoginLocationState | null)?.from?.pathname
  const destination = from && from !== '/login' ? from : '/home'

  const enterSystem = (token: string, user: Parameters<typeof setAuth>[1]) => {
    setAuth(token, user)
    const target = user.must_change_password ? '/profile?changePassword=required' : destination
    navigate(target, { replace: true })
  }

  const onFinish = async (values: LoginValues) => {
    if (demoEnabled) {
      if (!isDemoCredentials(values)) {
        message.error('演示账号或密码错误，请使用 admin / admin123')
        return
      }

      enterDemo()
      return
    }

    setLoading(true)
    try {
      const result = await authApi.login(values)
      enterSystem(result.token, result.user)
      message.success('登录成功')
    } finally {
      setLoading(false)
    }
  }

  const enterDemo = () => {
    enterSystem(demoToken, demoUser)
    message.success('已进入本地演示环境')
  }

  return (
    <main className="asset-login">
      <div className="asset-login__glow asset-login__glow--top" aria-hidden="true" />
      <div className="asset-login__glow asset-login__glow--bottom" aria-hidden="true" />

      <section className="asset-login__story" aria-labelledby="asset-login-title">
        <div className="asset-login__brand">
          <span className="asset-login__brand-mark">
            <Boxes aria-hidden="true" size={24} strokeWidth={1.9} />
          </span>
          <span>
            <strong>资产管理系统</strong>
            <small>ASSET OPERATIONS</small>
          </span>
        </div>

        <div className="asset-login__story-content">
          <span className="asset-login__eyebrow">
            <Sparkles aria-hidden="true" size={15} />
            企业资产数字化中台
          </span>
          <h1 id="asset-login-title">
            让每一件资产
            <br />
            都有清晰去向
          </h1>
          <p>从采购入库、领用流转到盘点报废，统一沉淀资产档案、责任人与操作轨迹。</p>

          <div className="asset-login__capabilities" aria-label="系统能力">
            {capabilityItems.map(({ icon: Icon, label }) => (
              <div key={label} className="asset-login__capability">
                <span>
                  <Icon aria-hidden="true" size={18} strokeWidth={1.9} />
                </span>
                <p>{label}</p>
                <CheckCircle2 aria-hidden="true" size={16} />
              </div>
            ))}
          </div>
        </div>

        <div className="asset-login__story-footer">
          <Building2 aria-hidden="true" size={17} />
          <span>面向企业多公司、多部门的统一资产管理</span>
        </div>
      </section>

      <section className="asset-login__access" aria-label="登录资产管理系统">
        <div className="asset-login__card">
          <div className="asset-login__card-heading">
            <span className="asset-login__mobile-brand">
              <Boxes aria-hidden="true" size={20} />
              资产管理系统
            </span>
            <span className="asset-login__secure-label">
              <Fingerprint aria-hidden="true" size={15} />
              安全访问
            </span>
            <h2>欢迎回来</h2>
            <p>登录后继续处理资产台账与待办事项</p>
          </div>

          <Form<LoginValues>
            className="asset-login__form"
            layout="vertical"
            requiredMark={false}
            onFinish={onFinish}
            initialValues={demoEnabled ? { ...demoCredentials } : undefined}
          >
            <Form.Item
              name="username"
              label="用户名"
              rules={[{ required: true, message: '请输入用户名' }]}
            >
              <Input
                size="large"
                autoComplete="username"
                prefix={<UserRound aria-hidden="true" size={18} />}
                placeholder="请输入用户名"
              />
            </Form.Item>
            <Form.Item
              name="password"
              label="密码"
              rules={[
                { required: true, message: '请输入密码' },
                { min: 6, message: '密码至少 6 位' },
              ]}
            >
              <Input.Password
                size="large"
                autoComplete="current-password"
                prefix={<LockKeyhole aria-hidden="true" size={18} />}
                placeholder="请输入密码"
              />
            </Form.Item>

            <Button
              className="asset-login__submit"
              type="primary"
              htmlType="submit"
              size="large"
              block
              loading={loading}
            >
              登录系统
              <ArrowRight aria-hidden="true" size={17} />
            </Button>
          </Form>

          {demoEnabled ? (
            <div className="asset-login__demo">
              <div className="asset-login__divider">
                <span>本地开发</span>
              </div>
              <Button className="asset-login__demo-button" size="large" block onClick={enterDemo}>
                <Sparkles aria-hidden="true" size={17} />
                体验演示数据
              </Button>
              <p>演示账号：admin / admin123，无需连接后端</p>
            </div>
          ) : null}

          <div className="asset-login__security-note">
            <ShieldCheck aria-hidden="true" size={17} />
            <span>账号信息将通过加密链路传输</span>
          </div>
        </div>

        <footer className="asset-login__footer">
          <span>© 2026 资产管理系统</span>
          <span>如需开通权限，请联系系统管理员</span>
        </footer>
      </section>
    </main>
  )
}
