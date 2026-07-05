import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/auth': 'http://localhost:8000',
      '/resume': 'http://localhost:8000',
      '/agent': 'http://localhost:8000',
      '/files': 'http://localhost:8000',
      '/analysis': 'http://localhost:8000',
    },
  },
})
