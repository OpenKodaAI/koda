import { expect, test } from "@playwright/test";
import {
  E2E_AGENT_ID,
  attachCheckpoint,
  expectNoConsoleIssues,
  expectNoHorizontalOverflow,
  gotoHealthy,
  installConsoleGuard,
} from "./helpers/koda-e2e";

test.describe("control plane agent configuration", () => {
  test("opens the seeded agent, edits a safe field and keeps secrets redacted", async ({ page }, testInfo) => {
    const consoleIssues = installConsoleGuard(page);
    await gotoHealthy(page, `/control-plane/agents/${E2E_AGENT_ID}`);
    await expect(page.getByRole("button", { name: /Identity|Identidade|Profile|Perfil/i })).toBeVisible({
      timeout: 15_000,
    });

    const nameInput = page.getByLabel(/Display name|Nome do Agente|Agent name/i);
    await expect(nameInput).toBeVisible();
    const displayName = `Atlas E2E ${Date.now()}`;
    await nameInput.fill(displayName);
    await page.getByRole("button", { name: /^Save$|^Salvar$/i }).click();
    await expect(page.locator("body")).toContainText(new RegExp(`Saved|Salvo|${displayName}`), {
      timeout: 15_000,
    });

    await page.getByRole("button", { name: /Skills|Habilidades/i }).click();
    await expect(page.locator("body")).toContainText(/skill|package|pacote/i, { timeout: 15_000 });
    await page.getByRole("button", { name: /Integrations|Integrações/i }).click();
    await expect(page.locator("body")).toContainText(/server|servidor|Telegram|MCP|integration/i, {
      timeout: 15_000,
    });

    const bodyText = await page.locator("body").innerText();
    expect(bodyText).not.toMatch(/e2e-control-plane-token-local-only|WEB_OPERATOR_SESSION_SECRET|POSTGRES_PASSWORD/i);
    await expectNoHorizontalOverflow(page);
    await attachCheckpoint(page, testInfo, "agent-editor");
    expectNoConsoleIssues(consoleIssues);
  });
});
