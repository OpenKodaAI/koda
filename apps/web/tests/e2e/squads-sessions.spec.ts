import { expect, test } from "@playwright/test";
import {
  E2E_AGENT_ID,
  attachCheckpoint,
  expectJsonOk,
  expectNoConsoleIssues,
  expectNoHorizontalOverflow,
  gotoHealthy,
  installConsoleGuard,
} from "./helpers/koda-e2e";

test.describe("sessions and squad surfaces", () => {
  test("sessions load with seeded executions and keep Delegate Task distinct from rooms", async ({
    page,
    request,
  }, testInfo) => {
    const consoleIssues = installConsoleGuard(page);
    const sessions = await expectJsonOk(
      request,
      `/api/control-plane/dashboard/agents/${encodeURIComponent(E2E_AGENT_ID)}/sessions?limit=20`,
    );
    const sessionRows = Array.isArray(sessions)
      ? sessions
      : Array.isArray((sessions as { items?: unknown[] }).items)
        ? (sessions as { items: unknown[] }).items
        : [];
    expect(sessionRows.length).toBeGreaterThan(0);

    await gotoHealthy(page, `/sessions?agent=${encodeURIComponent(E2E_AGENT_ID)}`);
    await expect(page.locator("body")).toContainText(/Sessions|Sessões|room|sala/i, { timeout: 15_000 });
    await expect(page.locator("body")).not.toContainText(/Delegate Task.*Squad Room|Squad Room.*Delegate Task/i);
    await expectNoHorizontalOverflow(page);
    await attachCheckpoint(page, testInfo, "sessions-squads");
    expectNoConsoleIssues(consoleIssues);
  });
});
