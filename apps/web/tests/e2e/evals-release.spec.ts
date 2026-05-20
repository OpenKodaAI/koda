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

type ExecutionSummary = { task_id?: number | string; query_text?: string };

function findSeededTaskId(payload: unknown): string {
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
  expect(match).toBeTruthy();
  return String(match?.task_id);
}

test.describe("evals, trajectory export and release quality", () => {
  test("creates an eval from a run, runs offline suite and exports a redacted trajectory", async ({
    page,
    request,
  }, testInfo) => {
    const consoleIssues = installConsoleGuard(page);
    const taskId = findSeededTaskId(
      await expectJsonOk(
        request,
        `/api/control-plane/dashboard/agents/${encodeURIComponent(E2E_AGENT_ID)}/executions?limit=100`,
      ),
    );

    const fromRun = await request.post(
      `/api/control-plane/agents/${encodeURIComponent(E2E_AGENT_ID)}/evals/cases/from-run`,
      {
        headers: sameOriginHeaders(),
        data: {
          task_id: Number(taskId),
          case_key: `e2e:browser:from-run:${Date.now()}`,
          status: "active",
          reference_answer: "Redacted E2E expected output",
        },
      },
    );
    expect(fromRun.status()).toBeLessThan(500);
    expect(fromRun.ok(), await fromRun.text()).toBeTruthy();

    await gotoHealthy(page, `/evaluations?agent=${encodeURIComponent(E2E_AGENT_ID)}`);
    await expect(page.getByRole("button", { name: /Run suite/i })).toBeEnabled({ timeout: 15_000 });
    await page.getByRole("button", { name: /Run suite/i }).click();
    await expect(page.getByRole("button", { name: /Run suite/i })).toBeEnabled({ timeout: 30_000 });
    await expect(page.locator("body")).toContainText(/Offline eval suite started|eval_run\.v1/i, { timeout: 20_000 });

    await expect(page.getByRole("button", { name: /Export trajectory/i })).toBeEnabled({ timeout: 20_000 });
    await page.getByRole("button", { name: /Export trajectory/i }).click();
    await expect(page.locator("body")).toContainText(/Redacted trajectory|trajectory_export\.v1|provider calls are disabled/i, {
      timeout: 20_000,
    });

    const release = await expectJsonOk(
      request,
      `/api/control-plane/agents/${encodeURIComponent(E2E_AGENT_ID)}/evals/release-quality/latest`,
    );
    expect(JSON.stringify(release)).toContain("release_quality.v1");

    await expectNoHorizontalOverflow(page);
    await attachCheckpoint(page, testInfo, "evals-release");
    expectNoConsoleIssues(consoleIssues);
  });
});
