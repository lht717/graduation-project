import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

// base 用相对路径，构建产物可直接放到 static/ 下任意子目录由 FastAPI 托管
export default defineConfig({
  base: "./",
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url))
    }
  },
  server: {
    port: 5173,
    host: true, // 允许局域网内其他电脑访问开发页面
    // 开发模式下 /api 与 /ws 转发到本机后端（生产模式由 FastAPI 直接托管，无需代理）
    proxy: {
      "/api": { target: "http://127.0.0.1:8080", changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:8080", ws: true }
    }
  }
});
