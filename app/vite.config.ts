import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Tauri 集成配置: 固定端口 1420, 与 tauri.conf.json devUrl 一致。
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    watch: {
      // 不监视 Rust 源, 避免重复触发
      ignored: ['**/src-tauri/**'],
    },
  },
})
