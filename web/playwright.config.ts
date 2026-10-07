import { defineConfig, devices } from '@playwright/test'

// Smoke tests run the real API in demo mode plus the built web app.
// From web/: npm run build && npm run e2e   (needs Python with the api/ requirements installed)
export default defineConfig({
  testDir: 'tests/e2e',
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: 'http://localhost:4173',
    trace: 'retain-on-failure',
    // Optional: point at an already-installed Chromium instead of `npx playwright install`.
    launchOptions: process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {},
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] }, testMatch: /(staff|borrowers)\.spec/ },
    { name: 'phone', use: { ...devices['Pixel 7'] }, testMatch: /portal\.spec/ },
  ],
  webServer: [
    { command: `${process.env.PYTHON ?? 'python'} -m uvicorn app.main:app --port 8000`, cwd: '../api', port: 8000, reuseExistingServer: false,
      env: { MCL_BACKEND: 'demo', MCL_SESSION_SECRET: 'e2e-secret', MCL_ALLOWED_ORIGINS: '["http://localhost:4173"]', MCL_DEV_SMS_INBOX: 'true' } },
    { command: 'npx vite preview --port 4173 --strictPort', port: 4173, reuseExistingServer: false },
  ],
})
