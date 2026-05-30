import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// В dev (npm run dev) проксируем API на бэкенд localhost:8080.
// В контейнере проксированием занимается nginx (см. nginx.conf).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8080',
      '/health': 'http://localhost:8080',
    },
  },
})
