import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
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
});
