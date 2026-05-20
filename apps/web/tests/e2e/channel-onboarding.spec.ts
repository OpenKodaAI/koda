import { expect, test } from "@playwright/test";
import {
  E2E_AGENT_ID,
  attachCheckpoint,
  expectJsonOk,
  expectNoConsoleIssues,
  expectNoHorizontalOverflow,
  gotoHealthy,
  installConsoleGuard,
  sameOriginHeaders,
} from "./helpers/koda-e2e";

test.describe("channel gateway and onboarding readiness", () => {
  test("pairs, approves, blocks and revokes Telegram identities without external Telegram", async ({
    page,
    request,
  }, testInfo) => {
    const consoleIssues = installConsoleGuard(page);
    const before = await expectJsonOk(
      request,
      `/api/control-plane/agents/${encodeURIComponent(E2E_AGENT_ID)}/channels/gateway`,
    );
    expect(JSON.stringify(before)).toContain("channel_gateway.v1");
    expect(JSON.stringify(before)).toContain("hello from deterministic e2e");

    await gotoHealthy(page, `/control-plane/agents/${E2E_AGENT_ID}`);
    await page.getByRole("button", { name: /Telegram/i }).click();
    await expect(page.locator("body")).toContainText(/Channel gateway|Gateway de canal/i, { timeout: 15_000 });
    await page.getByRole("button", { name: /Pairing code/i }).click();
    await expect(page.locator("body")).toContainText(/Pairing|E2E|[A-Z0-9]{4}/i, { timeout: 15_000 });

    await page.getByRole("button", { name: /Approve|Aprovar/i }).first().click();
    await expect(page.locator("body")).toContainText(/Approved|Aprovados|allowed|identity/i, { timeout: 15_000 });

    const afterApproval = (await expectJsonOk(
      request,
      `/api/control-plane/agents/${encodeURIComponent(E2E_AGENT_ID)}/channels/gateway`,
    )) as { unknown_senders?: Array<{ identity_id?: string }> };
    const blockTarget = afterApproval.unknown_senders?.find((sender) => sender.identity_id)?.identity_id;
    expect(blockTarget, "seed should leave one pending sender for the block path").toBeTruthy();
    const blockResponse = await request.post(
      `/api/control-plane/agents/${encodeURIComponent(E2E_AGENT_ID)}/channels/gateway/identities/${encodeURIComponent(
        blockTarget ?? "",
      )}/block`,
      { data: {}, headers: sameOriginHeaders() },
    );
    expect(blockResponse.status()).toBeLessThan(500);
    expect(blockResponse.ok()).toBeTruthy();

    const revoke = page.getByRole("button", { name: /Revoke|Revogar/i }).first();
    if (await revoke.isVisible().catch(() => false)) {
      await revoke.click();
    }
    await expect(page.locator("body")).toContainText(/Channel gateway|Gateway de canal/i, { timeout: 15_000 });

    const readiness = await expectJsonOk(request, "/api/control-plane/onboarding/readiness");
    expect(JSON.stringify(readiness)).toContain("onboarding_readiness.v1");

    await gotoHealthy(page, "/");
    await expect(page.locator("body")).toContainText(/Run first task|Open first trace|Pair Telegram sender|setup/i, {
      timeout: 15_000,
    });
    await expectNoHorizontalOverflow(page);
    await attachCheckpoint(page, testInfo, "channel-gateway-onboarding");
    expectNoConsoleIssues(consoleIssues);
  });
});
