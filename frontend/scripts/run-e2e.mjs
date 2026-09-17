import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(frontendRoot, "..");
const dbBasePath = path.resolve(repoRoot, ".runtime", "e2e", "qaltam-playwright.db");
const spawnCommand = process.platform === "win32" ? "npx.cmd" : "npx";

await fs.mkdir(path.dirname(dbBasePath), { recursive: true });
await Promise.all(
  [dbBasePath, `${dbBasePath}-shm`, `${dbBasePath}-wal`].map(async (target) => {
    await fs.rm(target, { force: true }).catch(() => undefined);
  }),
);

const child = spawn(spawnCommand, ["playwright", "test", "--config", "playwright.config.ts"], {
  cwd: frontendRoot,
  stdio: "inherit",
  env: process.env,
  shell: process.platform === "win32",
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});
