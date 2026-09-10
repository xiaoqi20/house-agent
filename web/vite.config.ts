import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // 后端固定 8010（本机 8000 被占用）：/api/v1 与 /healthz 代理到 FastAPI
    proxy: {
      '/api': { target: 'http://127.0.0.1:8010', changeOrigin: true },
      '/healthz': { target: 'http://127.0.0.1:8010', changeOrigin: true },
    },
  },
});
