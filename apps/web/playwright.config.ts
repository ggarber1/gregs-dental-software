import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:3000";
const isCI = !!process.env.CI;
const isRemote = !!process.env.E2E_BASE_URL;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // intake forms are stateful — run sequentially by default
  forbidOnly: isCI,
  retries: isCI ? 1 : 0,
  workers: 1,
  reporter: isCI ? [["github"], ["html", { open: "never" }]] : "list",

  globalSetup: "./e2e/global-setup.ts",

  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    storageState: "e2e/.auth/state.json",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  // Auto-start servers for local runs; skip when targeting remote
  ...(isRemote
    ? {}
    : {
        webServer: [
          {
            command: "pnpm dev",
            url: "http://localhost:3000",
            reuseExistingServer: true,
            timeout: 60_000,
          },
          {
            command: "uv run alembic upgrade head && uv run uvicorn app.main:app --port 8000",
            url: "http://localhost:8000/health",
            reuseExistingServer: true,
            timeout: 60_000,
            cwd: "../../apps/api",
          },
        ],
      }),
});
