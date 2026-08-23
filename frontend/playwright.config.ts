import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const frontendUrl = process.env.E2E_FRONTEND_URL ?? "http://127.0.0.1:3100";
const backendUrl = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:8100";
const frontendPort = new URL(frontendUrl).port || "3100";
const backendPort = new URL(backendUrl).port || "8100";
const uvCacheDir =
  process.env.UV_CACHE_DIR ?? path.resolve(process.cwd(), "..", ".tmp-uv-cache");
const databaseUrl =
  process.env.E2E_DATABASE_URL ??
  "postgresql+asyncpg://parksmart:parksmart@127.0.0.1:5432/parksmart_e2e";
const repositoryRoot = path.resolve(process.cwd(), "..");
const pythonExecutable = path.join(
  repositoryRoot,
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
const nextCli = path.join(process.cwd(), "node_modules", "next", "dist", "bin", "next");

export default defineConfig({
  testDir: "./e2e",
  testIgnore: ["**/auth.spec.ts"],
  fullyParallel: false,
  workers: 1,
  retries: 1,
  timeout: 120_000,
  expect: { timeout: 10_000 },
  outputDir: "test-results",
  reporter: [["line"], ["html", { open: "never" }]],
  use: {
    baseURL: frontendUrl,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "on-first-retry",
  },
  projects: [
    {
      name: "chromium-real-stack",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: `"${pythonExecutable}" -m uvicorn src.main:app --host 127.0.0.1 --port ${backendPort}`,
      cwd: "..",
      url: `${backendUrl}/health`,
      reuseExistingServer: true,
      timeout: 120_000,
      stdout: "ignore",
      stderr: "ignore",
      env: {
        ...process.env,
        DEMO_MODE: "true",
        SIMULATOR_ENABLED: "true",
        UV_CACHE_DIR: uvCacheDir,
        DATABASE_URL: databaseUrl,
      },
    },
    {
      command: `"${process.execPath}" "${nextCli}" start --hostname 127.0.0.1 --port ${frontendPort}`,
      url: frontendUrl,
      reuseExistingServer: true,
      timeout: 120_000,
      stdout: "ignore",
      stderr: "ignore",
      env: {
        ...process.env,
        NEXT_TELEMETRY_DISABLED: "1",
        NEXT_PUBLIC_DEMO_MODE: "true",
        PARKSMART_BACKEND_ORIGIN: backendUrl,
      },
    },
  ],
});
