import { spawnSync } from "node:child_process";
import path from "node:path";

const environment = {
  ...process.env,
  NEXT_TELEMETRY_DISABLED: "1",
  NEXT_PUBLIC_DEMO_MODE: "true",
  PARKSMART_BACKEND_ORIGIN:
    process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:8100",
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
 *
 * playwright.config.ts already owns:
 *   backend  -> http://127.0.0.1:8100
 *   frontend -> http://127.0.0.1:3100
 *
 * Having both this runner and Playwright start the same servers causes
 * duplicate server lifecycle ownership and can produce port/startup races.
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