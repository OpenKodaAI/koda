import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

/**
 * Stub-backed Playwright specs: the production build (`pnpm build:web` first)
 * served by `server.mjs` against `stub-control-plane.mjs`, so browser-only
 * behaviour can be checked in Chromium without the Docker stack.
 *
 *   pnpm --filter koda-web test:e2e:stub
 *
 * KODA_STUB_WEB_PORT and KODA_STUB_CONTROL_PLANE_PORT pick the ports;
 * KODA_E2E_CHROMIUM_PATH points at a Chromium other than Playwright's own.
 */
const webDir = path.resolve(__dirname, "../..");
const webPort = process.env.KODA_STUB_WEB_PORT ?? "3417";
const controlPlanePort = process.env.KODA_STUB_CONTROL_PLANE_PORT ?? "3418";

export default defineConfig({
  testDir: ".",
  outputDir: path.join(webDir, "test-results/e2e-stub"),
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  workers: 1,
  timeout: 60_000,
  reporter: [["list"]],
  use: {
    ...devices["Desktop Chrome"],
    baseURL: `http://127.0.0.1:${webPort}`,
    locale: "en-US",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: { executablePath: process.env.KODA_E2E_CHROMIUM_PATH || undefined },
  },
  webServer: [
    {
      command: `node tests/e2e-stub/stub-control-plane.mjs ${controlPlanePort}`,
      cwd: webDir,
      url: `http://127.0.0.1:${controlPlanePort}/health`,
      reuseExistingServer: false,
      timeout: 15_000,
    },
    {
      command: "node server.mjs",
      cwd: webDir,
      url: `http://127.0.0.1:${webPort}/login`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        NODE_ENV: "production",
        HOST: "127.0.0.1",
        PORT: webPort,
        CONTROL_PLANE_BASE_URL: `http://127.0.0.1:${controlPlanePort}`,
        WEB_OPERATOR_SESSION_SECRET: "e2e-stub-web-session-secret-local-only-0123456789",
      },
    },
  ],
});
