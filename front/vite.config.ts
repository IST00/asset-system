import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { createHtmlPlugin } from 'vite-plugin-html'
import { viteExternalsPlugin } from 'vite-plugin-externals'
import path from 'node:path'
import pkg from './package.json'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiPrefix = (env.VITE_API_PREFIX ?? '').replace(/\/+$/, '')
  const apiBase = (env.VITE_API_BASE_URL ?? '/api').replace(/\/+$/, '') || '/api'
  // Vite 代理需要拦截 `${prefix}${base}` 这段完整前缀，再把它剥掉后打到后端，
  // 保持跟生产 nginx 的行为一致（location /prefix/ + proxy_pass http://back/）。
  const proxyPath = `${apiPrefix}${apiBase}` || '/api'

  // 前端静态资源部署前缀。开发默认 '/'，生产通过 VITE_APP_BASE 注入 '/scaffold-ui/'。
  // Vite 把它写入 import.meta.env.BASE_URL，同时自动改写 index.html 与 import 引用。
  // 必须以 '/' 开头和结尾；这里做一次强制规范，避免尾部丢斜杠导致 nginx try_files 踩坑。
  const rawBase = env.VITE_APP_BASE || '/'
  const appBase = rawBase.endsWith('/') ? rawBase : `${rawBase}/`

  return {
    base: appBase,
    plugins: [
      viteExternalsPlugin({
        react: 'React',
        'react-dom': 'ReactDOM',
        '@soybean/common.main': 'SoybeanCommonMain',
      }),
      react(),
      createHtmlPlugin({
        inject: {
          data: {
            packageName: pkg.name,
            packageVersion: pkg.version,
            isProduction: mode === 'production',
          },
        },
      }),
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src'),
      },
    },
    build: {
      rollupOptions: {
        external: ['react', 'react-dom', '@soybean/common.main'],
        output: {
          globals: {
            react: 'React',
            'react-dom': 'ReactDOM',
            '@soybean/common.main': 'SoybeanCommonMain',
          },
        },
      },
    },
    server: {
      port: 3000,
      proxy: {
        [proxyPath]: {
          target: env.VITE_API_TARGET || 'http://localhost:8080',
          changeOrigin: true,
          // 剥掉 apiPrefix,让后端看到的路径跟线上 nginx 转发后一致(只剩 /api/...)
          rewrite: (p) => (apiPrefix ? p.replace(new RegExp(`^${apiPrefix}`), '') : p),
        },
      },
    },
  }
})
