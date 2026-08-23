import { defineConfig, devices } from "@playwright/test";

const frontendUrl = process.env.AUTH_E2E_FRONTEND_URL ?? "http://127.0.0.1:3200";
const frontendPort = new URL(frontendUrl).port || "3200";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/auth.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  outputDir: "test-results-auth",
  reporter: [["line"], ["html", { open: "never", outputFolder: "playwright-report-auth" }]],
  use: {
    baseURL: frontendUrl,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium-auth",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: `node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port ${frontendPort}`,
    url: frontendUrl,
    reuseExistingServer: true,
    timeout: 120_000,
    stdout: "ignore",
    stderr: "ignore",
    env: {
      ...process.env,
      NEXT_TELEMETRY_DISABLED: "1",
    },
  },
});
