import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiPrefix = (env.VITE_API_PREFIX ?? '').replace(/\/+$/, '')
  const apiBase = (env.VITE_API_BASE_URL ?? '/api').replace(/\/+$/, '') || '/api'
  // Vite 代理需要拦截 `${prefix}${base}` 这段完整前缀，再把它剥掉后打到后端，
  // 保持跟生产 nginx 的行为一致（location /prefix/ + proxy_pass http://back/）。
  const proxyPath = `${apiPrefix}${apiBase}` || '/api'

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src'),
      },
    },
    server: {
      port: 3000,
      proxy: {
        [proxyPath]: {
          target: env.VITE_API_TARGET || 'http://localhost:8080',
          changeOrigin: true,
          // 剥掉 apiPrefix，让后端看到的路径跟线上 nginx 转发后一致（只剩 /api/...）
          rewrite: (p) => (apiPrefix ? p.replace(new RegExp(`^${apiPrefix}`), '') : p),
        },
      },
    },
  }
})
