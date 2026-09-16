import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  use: {baseURL: 'http://127.0.0.1:8765', headless: true},
  webServer: {
    command: '../.venv/bin/uvicorn app.main:app --app-dir .. --host 127.0.0.1 --port 8765',
    url: 'http://127.0.0.1:8765/health',
    reuseExistingServer: false,
    env: {DATABASE_URL: 'sqlite+pysqlite:////tmp/patient-demo-browser-tests.db', APP_ENV: 'test'},
  },
});
