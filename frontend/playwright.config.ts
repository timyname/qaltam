import { defineConfig } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(frontendRoot, "..");
const isWindows = process.platform === "win32";
const pythonPath = isWindows
  ? path.join(repoRoot, ".venv", "Scripts", "python.exe")
  : path.join(repoRoot, ".venv", "bin", "python");
const npmCommand = isWindows ? "npm.cmd" : "npm";
const dbPath = path.resolve(repoRoot, ".runtime", "e2e", "qaltam-playwright.db");
const frontendPort = "43177";
const frontendUrl = `http://127.0.0.1:${frontendPort}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  reporter: [["list"]],
  use: {
    baseURL: frontendUrl,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    viewport: { width: 430, height: 932 },
  },
  webServer: [
    {
      command: `"${pythonPath}" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --ws none`,
      cwd: repoRoot,
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        DATABASE_URL: `sqlite+aiosqlite:///${dbPath.replace(/\\/g, "/")}`,
        TELEGRAM_WEBAPP_URL: `${frontendUrl}/`,
        DEEPSEEK_API_KEY: "",
      },
    },
    {
      command: `${npmCommand} run dev -- --host 127.0.0.1 --port ${frontendPort} --strictPort`,
      cwd: frontendRoot,
      url: frontendUrl,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        VITE_API_BASE_URL: "http://127.0.0.1:8000",
      },
    },
  ],
});
