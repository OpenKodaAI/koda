import { expect, test, type Page } from "@playwright/test";
import {
  E2E_EMAIL,
  E2E_PASSWORD,
  STORAGE_STATE,
  disableProductTour,
  ensureAuthStateDir,
  installConsoleGuard,
  readBootstrapCode,
} from "./helpers/koda-e2e";

async function fillBootstrapCode(page: Page, code: string) {
  const chars = code.replace(/-/g, "").split("");
  for (const [index, char] of chars.entries()) {
    await page.getByRole("textbox", { name: new RegExp(`Bootstrap code ${index + 1} / 12`, "i") }).fill(char);
  }
}

async function login(page: Page) {
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle").catch(() => undefined);
  const identifier = page.locator("#login-identifier");
  const password = page.locator("#login-password");
  await expect(identifier).toBeEditable({ timeout: 15_000 });
  await expect(password).toBeEditable({ timeout: 15_000 });
  await identifier.fill(E2E_EMAIL);
  await password.fill(E2E_PASSWORD);
  await expect(identifier).toHaveValue(E2E_EMAIL);
  await expect(password).toHaveValue(E2E_PASSWORD);
  const loginResponsePromise = page.waitForResponse((response) =>
    response.url().includes("/api/control-plane/auth/login"),
  );
  await page.getByRole("button", { name: /sign in|entrar|login/i }).click();
  const loginResponse = await loginResponsePromise;
  if (!loginResponse.ok()) {
    const responseText = await loginResponse.text().catch(() => "<unavailable>");
    const responseSnippet = responseText.length > 500 ? `${responseText.slice(0, 500)}...` : responseText;
    throw new Error(
      [
        `E2E login failed for ${E2E_EMAIL} with HTTP ${loginResponse.status()}.`,
        `Response: ${responseSnippet || "<empty>"}.`,
        "Run against a disposable seeded stack, or set KODA_E2E_EMAIL/KODA_E2E_PASSWORD to the seeded owner credentials before running Playwright.",
        "The password is intentionally not printed.",
      ].join(" "),
    );
  }
  await page
    .waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 5_000 })
    .catch(async () => {
      await page.goto("/", { waitUntil: "domcontentloaded" });
      await expect(page).toHaveURL((url) => !url.pathname.startsWith("/login"), { timeout: 10_000 });
    });
}

test("creates or reuses the local E2E owner session", async ({ page }) => {
  ensureAuthStateDir();
  await disableProductTour(page);
  const consoleIssues = installConsoleGuard(page);

  const authStatusResponse = await page.request.get("/api/control-plane/auth/status");
  if (authStatusResponse.ok()) {
    const authStatus = (await authStatusResponse.json()) as { authenticated?: boolean; has_owner?: boolean };
    if (authStatus.has_owner) {
      await login(page);
      await page.evaluate(() => {
        window.localStorage.setItem(
          "ui:onboarding-tour",
          JSON.stringify({
            version: 2,
            status: "skipped",
            currentStepId: null,
            completedChapters: [],
            updatedAt: Date.now(),
            completedAt: null,
            skippedAt: Date.now(),
          }),
        );
      });
      await page.context().storageState({ path: STORAGE_STATE });
      expect(consoleIssues.map((issue) => `${issue.type}: ${issue.text}`)).toEqual([]);
      return;
    }
  }

  await page.goto("/setup", { waitUntil: "domcontentloaded" });

  if (page.url().includes("/login")) {
    await login(page);
  } else if (await page.locator("#setup-email").isVisible({ timeout: 5_000 }).catch(() => false)) {
    await page.locator("#setup-email").fill(E2E_EMAIL);
    await page.locator("#setup-password").fill(E2E_PASSWORD);
    await page.locator("#setup-confirm").fill(E2E_PASSWORD);
    await fillBootstrapCode(page, readBootstrapCode());
    await page.getByRole("button", { name: /create|criar|continue|continuar/i }).click();

    const recoveryCheckbox = page.getByRole("checkbox").first();
    await expect(recoveryCheckbox).toBeVisible({ timeout: 15_000 });
    await recoveryCheckbox.check();
    await page.getByRole("button", { name: /continue|continuar|finish|concluir|workspace|espaço|espacio/i }).click();
    await expect(page).toHaveURL((url) => !url.pathname.startsWith("/setup"), { timeout: 15_000 });
  } else {
    await login(page);
  }

  await page.evaluate(() => {
    window.localStorage.setItem(
      "ui:onboarding-tour",
      JSON.stringify({
        version: 2,
        status: "skipped",
        currentStepId: null,
        completedChapters: [],
        updatedAt: Date.now(),
        completedAt: null,
        skippedAt: Date.now(),
      }),
    );
  });
  await page.context().storageState({ path: STORAGE_STATE });
  expect(consoleIssues.map((issue) => `${issue.type}: ${issue.text}`)).toEqual([]);
});
