/**
 * E2E de los recorridos criticos (AGENTS.md §Testing). Levanta tres procesos
 * locales: el Supabase Auth falso, la API real sobre SQLite nueva y el
 * frontend de Vite apuntando a ambos. Nada sale de la maquina.
 */
import { defineConfig, devices } from "@playwright/test";

const AUTH = "http://127.0.0.1:54321";
const PYTHON = process.env.E2E_PYTHON ?? "python";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    ...devices["Desktop Chrome"],
  },
  webServer: [
    { command: "node e2e/fake-auth.mjs", url: `${AUTH}/health`, reuseExistingServer: false },
    {
      command: `${PYTHON} ../backend/scripts/e2e_server.py`,
      url: "http://127.0.0.1:8000/docs",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "npx vite --host 127.0.0.1 --port 5173 --strictPort",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: false,
      env: { VITE_SUPABASE_URL: AUTH, VITE_SUPABASE_PUBLISHABLE_KEY: "e2e-publishable-key" },
    },
  ],
});
