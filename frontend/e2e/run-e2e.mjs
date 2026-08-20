import { spawnSync } from "node:child_process";
import path from "node:path";

const backendUrl =
  process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:8100";

const environment = {
  ...process.env,
  NEXT_TELEMETRY_DISABLED: "1",
  NEXT_PUBLIC_DEMO_MODE: "true",
  NEXT_PUBLIC_API_BASE_URL: "/api/v1",
  E2E_BACKEND_URL: backendUrl,
  E2E_API_URL:
    process.env.E2E_API_URL ?? `${backendUrl}/api/v1`,
  PARKSMART_BACKEND_ORIGIN: backendUrl,
};

const nextCli = path.resolve(
  "node_modules",
  "next",
  "dist",
  "bin",
  "next",
);

const playwrightCli = path.resolve(
  "node_modules",
  "@playwright",
  "test",
  "cli.js",
);

const repositoryRoot = path.resolve("..");

const pythonExecutable = path.join(
  repositoryRoot,
  ".venv",
  process.platform === "win32"
    ? "Scripts/python.exe"
    : "bin/python",
);

const databaseUrl =
  process.env.E2E_DATABASE_URL ??
  "postgresql+asyncpg://parksmart:parksmart@127.0.0.1:5432/parksmart_e2e";

const uvCacheDir =
  process.env.UV_CACHE_DIR ??
  path.join(repositoryRoot, ".tmp-uv-cache");

/*
 * Step 1:
 * Recreate the dedicated E2E database and seed its baseline data.
 *
 * Server lifecycle is NOT managed in this file.
 * playwright.config.ts owns backend/frontend webServer startup.
 */
const prepare = spawnSync(
  pythonExecutable,
  [
    path.join(
      repositoryRoot,
      "scripts",
      "prepare_e2e_database.py",
    ),
  ],
  {
    cwd: repositoryRoot,
    env: {
      ...environment,
      DATABASE_URL: databaseUrl,
      UV_CACHE_DIR: uvCacheDir,
    },
    stdio: "inherit",
  },
);

if (prepare.error) {
  console.error(
    "Failed to start E2E database preparation:",
    prepare.error,
  );
  process.exit(1);
}

if (prepare.status !== 0) {
  process.exit(prepare.status ?? 1);
}

/*
 * Step 2:
 * Produce the Next.js production build used by Playwright.
 *
 * NEXT_PUBLIC_API_BASE_URL is intentionally same-origin (/api/v1), so the
 * browser goes through next.config.ts and reaches the E2E backend configured
 * by PARKSMART_BACKEND_ORIGIN instead of the development fallback on :8000.
 */
const build = spawnSync(
  process.execPath,
  [
    nextCli,
    "build",
  ],
  {
    env: environment,
    stdio: "inherit",
  },
);

if (build.error) {
  console.error(
    "Failed to start Next.js production build:",
    build.error,
  );
  process.exit(1);
}

if (build.status !== 0) {
  process.exit(build.status ?? 1);
}

/*
 * Step 3:
 * Run Playwright.
 *
 * Do not manually spawn backend/frontend here.
 * playwright.config.ts owns:
 *   backend  -> E2E_BACKEND_URL (default 127.0.0.1:8100)
 *   frontend -> E2E_FRONTEND_URL (default 127.0.0.1:3100)
 */
const tests = spawnSync(
  process.execPath,
  [
    playwrightCli,
    "test",
    ...process.argv.slice(2),
  ],
  {
    env: environment,
    stdio: "inherit",
  },
);

if (tests.error) {
  console.error(
    "Failed to start Playwright:",
    tests.error,
  );
  process.exit(1);
}

process.exit(tests.status ?? 1);