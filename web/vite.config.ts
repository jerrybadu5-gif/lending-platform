/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

// The borrower portal is installable (PWA). The service worker only caches the app shell,
// never API answers, so nobody sees another session's money data from a cache.
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icon.svg'],
      manifest: {
        name: 'Breez Lending',
        short_name: 'Breez',
        description: 'See your Breez Lending loan, how to pay, and apply for a new loan.',
        start_url: '/portal',
        scope: '/',
        display: 'standalone',
        background_color: '#f5f6f4',
        theme_color: '#0b5d57',
        icons: [{ src: '/icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any maskable' }],
      },
      workbox: { navigateFallbackDenylist: [/^\/api\//], runtimeCaching: [] },
    }),
  ],
  server: { port: 5173, proxy: { '/api': 'http://localhost:8000' } },
  preview: { port: 4173, proxy: { '/api': 'http://localhost:8000' } },
  test: { environment: 'jsdom', include: ['tests/unit/**/*.test.tsx', 'tests/unit/**/*.test.ts'], setupFiles: ['tests/unit/setup.ts'] },
})
