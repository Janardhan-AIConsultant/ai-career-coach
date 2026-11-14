import { randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { defineConfig } from "@playwright/test";

// Random, per-run test credentials for a throwaway local database. Workers inherit these (??=).
process.env.JWT_SECRET_KEY ??= randomBytes(32).toString("hex");
process.env.E2E_ADMIN_EMAIL ??= "e2e-admin@example.com";
process.env.E2E_ADMIN_PASSWORD ??= `Aa1-${randomBytes(12).toString("hex")}`;

const venvPython = process.platform === "win32" ? "../backend/.venv/Scripts/python.exe" : "../backend/.venv/bin/python";
const python = process.env.E2E_PYTHON ?? (existsSync(venvPython) ? venvPython : "python");

export default defineConfig({
  testDir: "./e2e",
  testMatch: /.*\.spec\.ts/,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  workers: 1, // tests share one database and build on each other's data
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5173",
    // Uses the Microsoft Edge already installed on the machine; no browser download.
    // Override with E2E_BROWSER_CHANNEL=chrome (or unset it for Playwright's bundled Chromium).
    channel: process.env.E2E_BROWSER_CHANNEL ?? "msedge",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `"${python}" e2e/start_backend.py`,
      url: "http://localhost:8000/health",
      timeout: 120_000,
      reuseExistingServer: false,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: "npx vite --port 5173 --strictPort --host localhost",
      url: "http://localhost:5173",
      timeout: 60_000,
      reuseExistingServer: false,
      env: { VITE_API_BASE_URL: "http://localhost:8000" },
    },
  ],
});
