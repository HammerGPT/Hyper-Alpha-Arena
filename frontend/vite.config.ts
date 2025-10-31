import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react()],
  server: {
    port: 8802,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8802',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8802',
        changeOrigin: true,
        ws: true,
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./app"),
    },
  },
})
