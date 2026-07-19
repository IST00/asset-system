import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import '@/i18n'
import { appTheme } from '@/theme'
import './index.css'

const { app } = window.SoybeanCommonMain.alias

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 30_000 },
  },
})

export const Main = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigProvider locale={zhCN} theme={appTheme}>
        <BrowserRouter basename={import.meta.env.BASE_URL}>
          <App />
        </BrowserRouter>
      </ConfigProvider>
    </QueryClientProvider>
  )
}

app.setup(Main, {
  //
  boot: true,
  pay: false,
  allowEmptyToken: false,
  version: '',
  title: '',
  emptyButton: null,
  pageAutoEnd: false,
  scope: 'snsapi_base',
})
