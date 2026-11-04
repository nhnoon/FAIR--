import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The browser only ever talks to /api on its own origin; Vite forwards it to FastAPI.
// The Meta API key lives in backend/.env and never reaches the frontend.
// `npm run dev:replay` talks to the keyless replay server (backend: python -m scripts.demo_replay).
export default defineConfig(({ mode }) => {
  const BACKEND = process.env.FAIR_BACKEND_URL || (mode === 'replay' ? 'http://127.0.0.1:8010' : 'http://127.0.0.1:8000')
  return {
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
  }
})
