import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE ?? "http://localhost:3000",
    headless: true,
    screenshot: "only-on-failure",
  },
  webServer: process.env.CI
    ? {
        command: "npm run build && npm run start",
        port: 3000,
        reuseExistingServer: true,
        timeout: 120_000,
      }
    : undefined,
});
