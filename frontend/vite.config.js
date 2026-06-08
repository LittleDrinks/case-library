import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    allowedHosts: ["frontend"],
    proxy: {
      "/api": "http://app:8001",
    },
  },
});
