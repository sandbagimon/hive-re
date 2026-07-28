import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './web-e2e',
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:4173',
    headless: true,
  },
  webServer: [
    {
      command: '.venv/bin/python tests/run_web_e2e_server.py',
      url: 'http://127.0.0.1:8876/api/v1/health',
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      command: 'node_modules/.bin/vite preview --config frontend/vite.config.mjs',
      url: 'http://127.0.0.1:4173',
      reuseExistingServer: true,
      timeout: 30_000,
    },
  ],
});
