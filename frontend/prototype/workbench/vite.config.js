// 原型专用 AI 代理：只在 Vite dev server 的 Node 进程内读取主仓 .env，
// 浏览器只发同源 /prototype-ai/* 请求，密钥不进浏览器/日志/git。
// 目标 host 锁定为启动时解析出的 AI_BASE_URL，不接受任意 URL 转发。
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { createAiProxy } from "./server/ai-proxy.js";

export default defineConfig(({ mode }) => ({
  root: __dirname,
  base: "/prototype/workbench/",
  plugins: [vue(), createAiProxy()],
  cacheDir: "node_modules/.vite-prototype-workbench",
  server: { host: "0.0.0.0", port: 5179, strictPort: true },
}));
