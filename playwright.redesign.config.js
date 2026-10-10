import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
process.env.TEST_API_BASE_URL = "http://127.0.0.1:8001";
export default defineConfig({
  testDir: "./tests", testMatch: ["redesign/**/*.spec.js", "auth.spec.js", "health.spec.js"], workers: 1, timeout: 60000, reporter: "list",
  use: { baseURL: "http://127.0.0.1:5174", trace: "retain-on-failure" },
  webServer: [
    { command: "node scripts/backend.cjs --mock --port 8001", url: "http://127.0.0.1:8001/api/health", reuseExistingServer: false, env: { MOCK_DATABASE_PATH: path.resolve(".localdev/redesign-test-database.json"), MOCK_STORAGE_PATH: path.resolve(".localdev/redesign-test-uploads"), ALLOWED_ORIGIN: "http://127.0.0.1:5174" } },
    { command: "npm run dev --prefix frontend -- --port 5174 --strictPort", url: "http://127.0.0.1:5174", reuseExistingServer: false, env: { VITE_API_BASE_URL: "http://127.0.0.1:8001" } }
  ],
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }]
});
