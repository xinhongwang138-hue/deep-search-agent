import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发期把 /api 与 /ws 代理到后端，前端代码里无需写死 host
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true }
    }
  }
})
