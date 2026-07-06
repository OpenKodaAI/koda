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

type ExecutionSummary = { task_id?: number | string; query_text?: string };

function seededExecution(payload: unknown): ExecutionSummary {
  const rows = Array.isArray(payload)
    ? payload
    : Array.isArray((payload as { items?: unknown[] }).items)
      ? (payload as { items: unknown[] }).items
      : [];
  const match = rows.find(
    (row): row is ExecutionSummary =>
      typeof row === "object" &&
      row !== null &&
      String((row as ExecutionSummary).query_text ?? "").includes("E2E seeded parent execution"),
  );
  expect(match, "seed_e2e_data.py must create an E2E parent execution").toBeTruthy();
  return match;
}

test.describe("runtime execution detail, RunGraph and replay", () => {
  test("opens a seeded execution with RunGraph, child-run and replay data", async ({ page, request }, testInfo) => {
    const consoleIssues = installConsoleGuard(page);
    const execution = seededExecution(
      await expectJsonOk(
        request,
        `/api/control-plane/dashboard/agents/${encodeURIComponent(E2E_AGENT_ID)}/executions?limit=100`,
      ),
    );
    const taskId = String(execution.task_id);

    const detail = await expectJsonOk(
      request,
      `/api/control-plane/dashboard/agents/${encodeURIComponent(E2E_AGENT_ID)}/executions/${encodeURIComponent(taskId)}`,
    );
    expect(JSON.stringify(detail)).toContain("run_graph");
    expect(JSON.stringify(detail)).toContain("E2E");

    await gotoHealthy(page, `/executions?agent=${encodeURIComponent(E2E_AGENT_ID)}`);
    await expect(page.locator("body")).toContainText(/E2E seeded parent execution|RunGraph|Executions/i, {
      timeout: 15_000,
    });

    const row = page.getByText("E2E seeded parent execution").first();
    if (await row.isVisible().catch(() => false)) {
      await row.click();
      await expect(page.locator("body")).toContainText(/run_graph\.v1|RunGraph|Replay|Sandbox|Child/i, {
        timeout: 15_000,
      });
    }

    await expectNoHorizontalOverflow(page);
    await attachCheckpoint(page, testInfo, "runtime-execution-rungraph");
    expectNoConsoleIssues(consoleIssues);
  });
});
