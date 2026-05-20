import { expect, test } from "@playwright/test";
import {
  attachCheckpoint,
  expectNoConsoleIssues,
  expectNoHorizontalOverflow,
  gotoHealthy,
  installConsoleGuard,
} from "./helpers/koda-e2e";

test.describe("workspace directory import", () => {
  test("scans a fixture folder and imports selected prompt sources", async ({ page, request }, testInfo) => {
    const consoleIssues = installConsoleGuard(page);
    const fixturePath =
      process.env.KODA_E2E_WORKSPACE_IMPORT_FIXTURE ??
      "/workspace/tests/fixtures/workspace-directory-import/sample-repo";

    await gotoHealthy(page, "/control-plane");
    await page.getByRole("button", { name: /^Criar$|^Create$/i }).click();
    await page.getByRole("menuitem", { name: /Import from folder|Importar/i }).click();

    const dialog = page.getByRole("dialog").filter({ hasText: /Import from folder|Importar/i });
    await expect(dialog).toBeVisible();
    await dialog.getByLabel(/Folder path|Caminho/i).fill(fixturePath);
    await dialog.getByRole("button", { name: /^Scan$|^Escanear$/i }).click();

    await expect(dialog.getByText("AGENTS.md")).toBeVisible({ timeout: 15_000 });
    await expect(dialog.getByText("CLAUDE.md")).toBeVisible();
    await expect(dialog.getByText(".cursor/rules/python.mdc")).toBeVisible();
    await expect(dialog.getByText(".mcp.json")).toBeVisible();
    await expect(dialog.getByText(".claude/settings.json")).toBeVisible();
    await expect(dialog.getByText(/codex/i)).toBeVisible();
    await expect(dialog.getByText(/claude/i).first()).toBeVisible();
    await expect(dialog.getByText(/cursor/i)).toBeVisible();
    await expect(dialog.getByText(/blocked/i)).toBeVisible();
    await expect(dialog.getByText(/koda:workspace-import:start/i)).toBeVisible();

    await expect(
      dialog.locator("section", { hasText: /Blocked|Bloqueado/i }).locator("input[type='checkbox']"),
    ).toHaveCount(0);

    await dialog.getByRole("button", { name: /^Import$|^Importar$/i }).click();
    await expect(dialog).toHaveCount(0, { timeout: 15_000 });

    const workspacesResponse = await request.get("/api/control-plane/workspaces");
    expect(workspacesResponse.ok()).toBeTruthy();
    const workspaces = await workspacesResponse.json();
    const workspaceItems = (workspaces.items ?? []) as Array<{
      root_path?: string;
      root_exists?: boolean;
      scan_status?: string;
      documents?: { system_prompt_md?: string };
    }>;
    const imported = [...workspaceItems].reverse().find((workspace) => workspace.root_path === fixturePath);
    expect(imported?.root_exists).toBe(true);
    expect(imported?.scan_status).toBe("completed");
    expect(imported?.documents?.system_prompt_md).toContain("koda:workspace-import:start");
    expect(imported?.documents?.system_prompt_md).toContain("AGENTS.md");
    expect(imported?.documents?.system_prompt_md).toContain("CLAUDE.md");

    await expectNoHorizontalOverflow(page);
    await attachCheckpoint(page, testInfo, "workspace-directory-import");
    expectNoConsoleIssues(consoleIssues);
  });
});
