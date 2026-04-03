import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: resolve(__dirname, '../frontend'),
    emptyOutDir: false,  // don't wipe vanilla JS files — coexist during migration
    rollupOptions: {
      output: {
        assetFileNames: 'assets/[name]-[hash][extname]',
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
      },
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/session': 'http://localhost:8000',
      '/user': 'http://localhost:8000',
      '/chat': 'http://localhost:8000',
      '/skills': 'http://localhost:8000',
      '/vault': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
