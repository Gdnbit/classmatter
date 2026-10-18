import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// Public candidate: no embedded editor/telemetry scripts or inline source maps.
export default defineConfig({
  base: process.env.FIGMA_PUBLIC_URL ? `${process.env.FIGMA_PUBLIC_URL}/` : '/',
  plugins: [react(), tailwindcss()],
  build: { sourcemap: false },
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: { host: '127.0.0.1', port: Number(process.env.PORT || 8443), strictPort: true },
  preview: { host: '127.0.0.1', port: Number(process.env.PORT || 8443), strictPort: true },
})
