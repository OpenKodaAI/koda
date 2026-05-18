import { expect, test } from "@playwright/test";
import {
  attachCheckpoint,
  E2E_EMAIL,
  E2E_PASSWORD,
  STORAGE_STATE,
  expectNoConsoleIssues,
  expectNoHorizontalOverflow,
  gotoHealthy,
  installConsoleGuard,
  sameOriginHeaders,
} from "./helpers/koda-e2e";

/**
 * Authenticated smoke specs prove the full dashboard shell works against the
 * local Docker E2E stack.
 */

test.describe("smoke @smoke", () => {
  test("dashboard home renders without console errors or overflow", async ({ page }, testInfo) => {
    const consoleIssues = installConsoleGuard(page);
    await gotoHealthy(page, "/");
    await expect(page).toHaveTitle(/koda/i);
    await expectNoHorizontalOverflow(page);
    await attachCheckpoint(page, testInfo, "home");
    expectNoConsoleIssues(consoleIssues);
  });

  test("auth session can sign out and sign back in", async ({ page, request }) => {
    const consoleIssues = installConsoleGuard(page);
    await gotoHealthy(page, "/");
    await page.getByTestId("account-menu-trigger").click();
    await page.getByTestId("account-menu-sign-out").click();

    await expect
      .poll(
        async () => {
          try {
            return (await request.get("/api/health")).ok();
          } catch {
            return false;
          }
        },
        { timeout: 45_000 },
      )
      .toBe(true);
    await request.post("/api/control-plane/auth/logout", {
      data: {},
      headers: sameOriginHeaders(),
    });
    await page.goto("/login", { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle").catch(() => undefined);
    await page.locator("#login-identifier").fill(E2E_EMAIL);
    await page.locator("#login-password").fill(E2E_PASSWORD);
    await page.getByRole("button", { name: /sign in|entrar|login/i }).click();
    await expect(page).toHaveURL((url) => !url.pathname.startsWith("/login"), { timeout: 15_000 });
    await page.context().storageState({ path: STORAGE_STATE });
    expectNoConsoleIssues(consoleIssues);
  });
});
