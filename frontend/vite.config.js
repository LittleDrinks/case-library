import { resolve } from "node:path";
import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";
import { prototypeAgentApi } from "./prototype-agent-api.mjs";

export default defineConfig(({ mode }) => {
  const repositoryRoot = resolve(import.meta.dirname, "..");
  const env = loadEnv(mode, repositoryRoot, "");
  return {
    plugins: [vue(), prototypeAgentApi(env, repositoryRoot)],
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        "/api": process.env.VITE_API_PROXY || "http://app:8001",
      },
    },
    test: {
      environment: "jsdom",
      include: ["src/**/*.test.js"],
    },
  };
});
