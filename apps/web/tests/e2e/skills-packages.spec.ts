import { expect, test } from "@playwright/test";
import {
  E2E_AGENT_ID,
  attachCheckpoint,
  expectNoConsoleIssues,
  expectNoHorizontalOverflow,
  gotoHealthy,
  installConsoleGuard,
} from "./helpers/koda-e2e";

test.describe("skills package scanner and installer", () => {
  test("scans a safe local package and denies an unsafe package path", async ({ page }, testInfo) => {
    const consoleIssues = installConsoleGuard(page, {
      allow: [/Failed to load resource: the server responded with a status of 400 \(Bad Request\)/],
    });
    await gotoHealthy(page, `/control-plane/agents/${E2E_AGENT_ID}`);
    await page.getByRole("button", { name: /Skills|Habilidades/i }).click();
    await expect(page.locator("body")).toContainText(/Skill packages|Pacotes de skill|package/i, { timeout: 15_000 });

    const packagePath = page.getByLabel(/Package path|Caminho do pacote/i);
    await packagePath.fill("/workspace/examples/skills/safe-readonly");
    await page.getByRole("button", { name: /^Scan$|^Escanear$/i }).click();
    await expect(page.getByText(/E2E Safe Readonly|Safe Readonly|safe-readonly/i).first()).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText(/allow/i)).toBeVisible();
    await page.getByRole("button", { name: /^Install|Install after review|Instalar/i }).click();
    await expect(page.getByText(/safe-readonly|e2e\.safe-readonly/i)).toBeVisible({ timeout: 15_000 });

    await packagePath.fill("../../../../etc/passwd");
    await page.getByRole("button", { name: /^Scan$|^Escanear$/i }).click();
    await expect(page.locator("body")).toContainText(/validation|denied|path|traversal|manifest|failed/i, {
      timeout: 15_000,
    });

    await expectNoHorizontalOverflow(page);
    await attachCheckpoint(page, testInfo, "skills-packages");
    expectNoConsoleIssues(consoleIssues);
  });
});
