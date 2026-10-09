import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

export default defineConfig({
  testDir: "./tests",
  globalSetup: "./tests/global-setup.js",
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "on-first-retry"
  },
  webServer: [
    {
      command: "node scripts/backend.cjs",
      url: "http://127.0.0.1:8000/api/health",
      timeout: 120000,
      reuseExistingServer: false,
      env: {
        USE_MOCK_AWS: "true",
        USE_REAL_DATABASE: "false",
        USE_REAL_STORAGE: "false",
        USE_REAL_LLM: "false",
        MOCK_DATABASE_PATH: path.resolve(".localdev/playwright-database.json"),
        MOCK_STORAGE_PATH: path.resolve(".localdev/playwright-uploads")
      }
    },
    {
      command: "npm run dev",
      cwd: "frontend",
      url: "http://127.0.0.1:5173",
      timeout: 120000,
      reuseExistingServer: true,
      env: {
        VITE_API_BASE_URL: "http://127.0.0.1:8000"
      }
    }
  ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] }
    }
  ]
});
