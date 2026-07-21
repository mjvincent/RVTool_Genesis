import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 3000,
    proxy: {
      // container-to-container; accessible on the host at :8001
      "/api": {
        target: "http://api:8000",
        changeOrigin: true,
      },
    },
  },
  // preview serves the compiled dist/ in production containers.
  // Mirrors server.proxy so /api requests are forwarded to the API container.
  preview: {
    host: "0.0.0.0",
    port: 3000,
    proxy: {
      "/api": {
        target: "http://api:8000",
        changeOrigin: true,
      },
    },
  },
  css: {
    preprocessorOptions: {
      scss: {
        quietDeps: true,
      },
    },
  },
});
