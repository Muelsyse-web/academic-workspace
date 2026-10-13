import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:8766",
    channel: "chrome",
    trace: "retain-on-failure",
  },
  projects: [{ name: "desktop", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "../.venv/bin/python ../scripts/e2e_server.py",
      url: "http://127.0.0.1:8766/api/v1/health",
      reuseExistingServer: false,
      timeout: 30000,
    },
    {
      command: "../.venv/bin/python ../scripts/mock_model_server.py",
      url: "http://127.0.0.1:18765/v1/models",
      reuseExistingServer: false,
      timeout: 30000,
    },
  ],
});
