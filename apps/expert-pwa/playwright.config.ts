import { defineConfig, devices } from '@playwright/test';

import { BACKEND_ENV, PWA_ORIGIN } from './tests/e2e/env';

const CI = Boolean(process.env.CI);

/**
 * End-to-end tests against the real backend, PostgreSQL and Mailpit, with the
 * production PWA build served by `vite preview` (same-origin /api proxy).
 * WebKit with iPhone emulation approximates Safari; it does not replace a real device.
 */
export default defineConfig({
  testDir: 'tests/e2e',
  fullyParallel: false,
  workers: 1,
  forbidOnly: CI,
  retries: CI ? 1 : 0,
  reporter: CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  globalSetup: './tests/e2e/global-setup.ts',
  use: { baseURL: PWA_ORIGIN, trace: 'retain-on-failure' },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'webkit-iphone', use: { ...devices['iPhone 15'] } },
  ],
  webServer: [
    {
      command:
        'uv run --directory ../../backend uvicorn app.main:create_app --factory --port 8000 --timeout-keep-alive 75',
      url: 'http://localhost:8000/api/v1/health',
      env: BACKEND_ENV,
      reuseExistingServer: !CI,
    },
    {
      command: 'npm run build && npm run preview',
      url: PWA_ORIGIN,
      reuseExistingServer: !CI,
      timeout: 120_000,
    },
  ],
});
