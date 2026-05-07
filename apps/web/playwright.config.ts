import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for koda-web E2E tests.
 *
 * To enable, run:
 *   pnpm --filter web add -D @playwright/test
 *   pnpm --filter web exec playwright install chromium
 *   pnpm --filter web test:e2e
 *
 * The repo's Next dev server lives at http://127.0.0.1:3000 by default.
 * Specs under tests/e2e/ assume a Python backend running in KODA_TEST=1 mode
 * (see tests/e2e/README.md).
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: process.env.KODA_WEB_BASE_URL ?? "http://127.0.0.1:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: process.env.PLAYWRIGHT_SKIP_WEB_SERVER
    ? undefined
    : {
        command: "pnpm --filter web dev",
        url: "http://127.0.0.1:3000",
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
