import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    // 第 7 步性能优化（7a）：跨源隔离响应头，让 SharedArrayBuffer 可用，
    // 3DGS 排序 worker 才能共享内存（不开启则 gaussian-splats-3d 会回退到慢速路径）。
    // 注意：以后集成进主站（FastAPI 托管）时，主站服务也要加这两个头。
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    },
  },
})
