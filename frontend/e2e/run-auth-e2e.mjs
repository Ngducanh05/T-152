import { spawnSync } from "node:child_process";
import path from "node:path";

const environment = {
  ...process.env,
  NEXT_TELEMETRY_DISABLED: "1",
  NEXT_PUBLIC_DEMO_MODE: "false",
  NEXT_PUBLIC_API_BASE_URL: "http://api.parksmart.test/api/v1",
  NEXT_PUBLIC_SUPABASE_URL: "http://supabase.parksmart.test",
  NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "public-e2e-key",
};
const nextCli = path.resolve("node_modules", "next", "dist", "bin", "next");
const playwrightCli = path.resolve("node_modules", "@playwright", "test", "cli.js");

const build = spawnSync(process.execPath, [nextCli, "build"], {
  env: environment,
  stdio: "inherit",
});
if (build.status !== 0) process.exit(build.status ?? 1);

const tests = spawnSync(
  process.execPath,
  [playwrightCli, "test", "--config=playwright.auth.config.ts", ...process.argv.slice(2)],
  { env: environment, stdio: "inherit" },
);
process.exit(tests.status ?? 1);
