import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端端口：默认与 main.py 一致（8000）；本机 8000 被占用时用
// DS_AGENT_API_PORT=8002 覆盖，无需改本文件。
const apiPort = process.env.DS_AGENT_API_PORT || '8000'
const apiTarget = `http://127.0.0.1:${apiPort}`
const wsTarget = `ws://127.0.0.1:${apiPort}`

// 开发期把 /api 与 /ws 代理到后端，前端代码里无需写死 host
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    host: '127.0.0.1',
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
      '/ws': { target: wsTarget, ws: true }
    }
  }
})
