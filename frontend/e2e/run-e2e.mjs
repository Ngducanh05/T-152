import { spawn, spawnSync } from "node:child_process";
import path from "node:path";

const environment = {
  ...process.env,
  NEXT_TELEMETRY_DISABLED: "1",
  NEXT_PUBLIC_ENABLE_TEST_HARNESS: "true",
  PARKSMART_BACKEND_ORIGIN:
    process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:8100",
};
const nextCli = path.resolve("node_modules", "next", "dist", "bin", "next");
const playwrightCli = path.resolve("node_modules", "@playwright", "test", "cli.js");
const repositoryRoot = path.resolve("..");
const pythonExecutable = path.join(
  repositoryRoot,
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
const databaseUrl =
  process.env.E2E_DATABASE_URL ??
  "postgresql+asyncpg://parksmart:parksmart@127.0.0.1:5432/parksmart_e2e";
const backendUrl = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:8100";
const frontendUrl = process.env.E2E_FRONTEND_URL ?? "http://127.0.0.1:3100";
const backendPort = new URL(backendUrl).port || "8100";
const frontendPort = new URL(frontendUrl).port || "3100";
const uvCacheDir =
  process.env.UV_CACHE_DIR ?? path.join(repositoryRoot, ".tmp-uv-cache");

const prepare = spawnSync(
  pythonExecutable,
  [path.join(repositoryRoot, "scripts", "prepare_e2e_database.py")],
  {
    cwd: repositoryRoot,
    env: { ...environment, DATABASE_URL: databaseUrl, UV_CACHE_DIR: uvCacheDir },
    stdio: "inherit",
  },
);
if (prepare.status !== 0) process.exit(prepare.status ?? 1);

const build = spawnSync(process.execPath, [nextCli, "build"], {
  env: environment,
  stdio: "inherit",
});
if (build.status !== 0) process.exit(build.status ?? 1);

const backend = spawn(
  pythonExecutable,
  ["-m", "uvicorn", "src.main:app", "--host", "127.0.0.1", "--port", backendPort],
  {
    cwd: repositoryRoot,
    detached: process.platform !== "win32",
    env: {
      ...environment,
      DATABASE_URL: databaseUrl,
      DEMO_MODE: "true",
      SIMULATOR_ENABLED: "true",
      UV_CACHE_DIR: uvCacheDir,
    },
    stdio: "ignore",
  },
);
const frontend = spawn(
  process.execPath,
  [nextCli, "start", "--hostname", "127.0.0.1", "--port", frontendPort],
  {
    detached: process.platform !== "win32",
    env: environment,
    stdio: "ignore",
  },
);

function stopTree(child) {
  if (!child.pid) return;
  if (process.platform === "win32") {
    spawnSync("taskkill.exe", ["/PID", String(child.pid), "/T", "/F"], {
      stdio: "ignore",
    });
    return;
  }
  try {
    process.kill(-child.pid, "SIGTERM");
  } catch {
    // The process group has already stopped.
  }
}

const tests = spawnSync(
  process.execPath,
  [playwrightCli, "test", ...process.argv.slice(2)],
  { env: environment, stdio: "inherit" },
);
stopTree(frontend);
stopTree(backend);
process.exit(tests.status ?? 1);
