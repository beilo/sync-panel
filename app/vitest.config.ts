import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// 测试配置: jsdom 环境 + 全局 setup (mock invoke -> 真 sidecar)。
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    // e2e 真跑 sidecar exe, 给足超时
    testTimeout: 30000,
  },
});
