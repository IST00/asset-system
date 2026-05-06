import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
export default defineConfig(function (_a) {
    var _b;
    var _c, _d;
    var mode = _a.mode;
    var env = loadEnv(mode, process.cwd(), '');
    var apiPrefix = ((_c = env.VITE_API_PREFIX) !== null && _c !== void 0 ? _c : '').replace(/\/+$/, '');
    var apiBase = ((_d = env.VITE_API_BASE_URL) !== null && _d !== void 0 ? _d : '/api').replace(/\/+$/, '') || '/api';
    // Vite 代理需要拦截 `${prefix}${base}` 这段完整前缀，再把它剥掉后打到后端，
    // 保持跟生产 nginx 的行为一致（location /prefix/ + proxy_pass http://back/）。
    var proxyPath = "".concat(apiPrefix).concat(apiBase) || '/api';
    // 前端静态资源部署前缀。开发默认 '/'，生产通过 VITE_APP_BASE 注入 '/scaffold-ui/'。
    // Vite 把它写入 import.meta.env.BASE_URL，同时自动改写 index.html 与 import 引用。
    // 必须以 '/' 开头和结尾；这里做一次强制规范，避免尾部丢斜杠导致 nginx try_files 踩坑。
    var rawBase = env.VITE_APP_BASE || '/';
    var appBase = rawBase.endsWith('/') ? rawBase : "".concat(rawBase, "/");
    return {
        base: appBase,
        plugins: [react()],
        resolve: {
            alias: {
                '@': path.resolve(__dirname, 'src'),
            },
        },
        server: {
            port: 3000,
            proxy: (_b = {},
                _b[proxyPath] = {
                    target: env.VITE_API_TARGET || 'http://localhost:8080',
                    changeOrigin: true,
                    // 剥掉 apiPrefix，让后端看到的路径跟线上 nginx 转发后一致（只剩 /api/...）
                    rewrite: function (p) { return (apiPrefix ? p.replace(new RegExp("^".concat(apiPrefix)), '') : p); },
                },
                _b),
        },
    };
});
