import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, path.resolve(__dirname, '..'), '')
  return {
    plugins: [react()],
    base: '/',
    publicDir: 'public',
    envDir: path.resolve(__dirname, '..'),
    // Expose GOOGLE_CLIENT_ID / APPLE_CLIENT_ID from root .env to the client bundle.
    envPrefix: ['VITE_', 'GOOGLE_', 'APPLE_'],
    define: {
      'import.meta.env.VITE_GOOGLE_CLIENT_ID': JSON.stringify(
        env.VITE_GOOGLE_CLIENT_ID || env.GOOGLE_CLIENT_ID || '',
      ),
      'import.meta.env.VITE_APPLE_CLIENT_ID': JSON.stringify(
        env.VITE_APPLE_CLIENT_ID || env.APPLE_CLIENT_ID || '',
      ),
    },
    server: {
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
          cookieDomainRewrite: 'localhost',
        },
      },
    },
  }
})
