import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  const validatePublicBase = (value: string | undefined, protocols: string[], name: string) => {
    if (!value?.trim()) return
    const parsed = new URL(value)
    if (!protocols.includes(parsed.protocol) || parsed.pathname !== '/' || parsed.search || parsed.hash || parsed.username || parsed.password) {
      throw new Error(`${name} is invalid`)
    }
    if (mode === 'production' && !['https:', 'wss:'].includes(parsed.protocol)) {
      throw new Error(`${name} must use a secure protocol in production`)
    }
  }
  validatePublicBase(process.env.VITE_API_BASE_URL ?? env.VITE_API_BASE_URL, ['http:', 'https:'], 'VITE_API_BASE_URL')
  validatePublicBase(process.env.VITE_WS_BASE_URL ?? env.VITE_WS_BASE_URL, ['ws:', 'wss:'], 'VITE_WS_BASE_URL')
  const backend = env.VITE_DEV_BACKEND_URL || 'http://localhost:8000'
  const parsed = new URL(backend)
  if (!['http:', 'https:'].includes(parsed.protocol) || parsed.pathname !== '/' || parsed.search || parsed.hash || parsed.username || parsed.password) {
    throw new Error('VITE_DEV_BACKEND_URL must be an HTTP(S) origin')
  }
  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api': { target: parsed.origin, changeOrigin: true },
        '/ws': { target: parsed.origin, changeOrigin: true, ws: true },
      },
    },
  }
})
