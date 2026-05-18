import { expect, test } from "@playwright/test";
import {
  E2E_AGENT_ID,
  expectNoConsoleIssues,
  expectNoHorizontalOverflow,
  gotoHealthy,
  installConsoleGuard,
  sameOriginHeaders,
} from "./helpers/koda-e2e";

test.describe("approval and policy deny paths", () => {
  test("renders session surfaces and fail-closes unknown approval actions", async ({ page, request }) => {
    const consoleIssues = installConsoleGuard(page);

    const listResponse = await request.get(
      `/api/control-plane/dashboard/agents/${encodeURIComponent(E2E_AGENT_ID)}/approvals`,
    );
    expect(listResponse.status()).toBeLessThan(500);
    const listPayload = await listResponse.json();
    expect(Array.isArray(listPayload.items ?? [])).toBe(true);

    const unknownResponse = await request.post(
      `/api/control-plane/dashboard/agents/${encodeURIComponent(E2E_AGENT_ID)}/approvals/e2e-missing-approval`,
      {
        headers: sameOriginHeaders(),
        data: {
          decision: "approve",
          rationale: "E2E must not execute an unknown approval id.",
        },
      },
    );
    expect(unknownResponse.status()).toBeGreaterThanOrEqual(400);
    expect(unknownResponse.status()).toBeLessThan(500);

    await gotoHealthy(page, "/sessions");
    await expect(page.locator("body")).toContainText(/Sessions|Sessões|session|room/i, { timeout: 15_000 });
    await expectNoHorizontalOverflow(page);
    expectNoConsoleIssues(consoleIssues);
  });
});
