import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Button, Result, Spin } from 'antd'
import { feishuApi } from '@/api/feishu'
import { useAuthStore } from '@/store/auth'

export default function FeishuCallback() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const setAuth = useAuthStore((state) => state.setAuth)
  const [error, setError] = useState('')
  const exchanged = useRef(false)

  useEffect(() => {
    if (exchanged.current) {
      return
    }
    exchanged.current = true
    const code = searchParams.get('code')
    if (!code) {
      setError('飞书授权码缺失，请重新登录')
      return
    }

    const exchange = async () => {
      try {
        const result = await feishuApi.exchange(code)
        setAuth(result.token, result.user)
        navigate(result.user.must_change_password ? '/profile?changePassword=required' : '/home', {
          replace: true,
        })
      } catch {
        setError('飞书登录失败，请确认账号已绑定或重新授权')
      }
    }

    void exchange()
  }, [navigate, searchParams, setAuth])

  if (error) {
    return (
      <Result
        status="error"
        title="登录失败"
        subTitle={error}
        extra={
          <Button type="primary" onClick={() => navigate('/login', { replace: true })}>
            返回登录
          </Button>
        }
      />
    )
  }

  return (
    <div style={{ alignItems: 'center', display: 'grid', minHeight: '100vh' }}>
      <Spin size="large" tip="正在使用飞书身份登录..." />
    </div>
  )
}
