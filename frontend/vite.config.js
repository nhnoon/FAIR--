import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The browser only ever talks to /api on its own origin; Vite forwards it to FastAPI.
// The Meta API key lives in backend/.env and never reaches the frontend.
const BACKEND = process.env.FAIR_BACKEND_URL || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: BACKEND, changeOrigin: true } },
  },
  preview: {
    proxy: { '/api': { target: BACKEND, changeOrigin: true } },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    css: false,
    testTimeout: 20000,
  },
})
