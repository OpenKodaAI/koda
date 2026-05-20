import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { expect, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";

export const E2E_AGENT_ID = process.env.KODA_E2E_AGENT_ID ?? "DEMO_ATLAS";
export const E2E_EMAIL = process.env.KODA_E2E_EMAIL ?? "owner-e2e@koda.local";
export const E2E_PASSWORD = process.env.KODA_E2E_PASSWORD ?? "Koda-E2E-local-only-2026!";
export const STORAGE_STATE = "tests/e2e/.auth/operator.json";

type ConsoleIssue = {
  type: "console" | "pageerror";
  text: string;
};

type ConsoleGuardOptions = {
  allow?: RegExp[];
};

export function repoRoot(): string {
  if (process.env.KODA_REPO_ROOT) return process.env.KODA_REPO_ROOT;
  return path.resolve(process.cwd(), "../..");
}

export function sameOriginHeaders(): Record<string, string> {
  const origin = new URL(process.env.KODA_WEB_BASE_URL ?? "http://127.0.0.1:3000").origin;
  return {
    origin,
    referer: `${origin}/`,
  };
}

export function ensureAuthStateDir(): void {
  fs.mkdirSync(path.join(process.cwd(), "tests/e2e/.auth"), { recursive: true });
}

export function readBootstrapCode(): string {
  if (process.env.KODA_E2E_BOOTSTRAP_CODE) {
    return process.env.KODA_E2E_BOOTSTRAP_CODE.trim();
  }
  const project = process.env.KODA_E2E_COMPOSE_PROJECT ?? "koda-e2e";
  const envFile = process.env.KODA_E2E_ENV_FILE ?? ".env.e2e.local";
  const output = execFileSync(
    "docker",
    [
      "compose",
      "-p",
      project,
      "--env-file",
      envFile,
      "-f",
      "docker-compose.yml",
      "-f",
      "docker-compose.dev.yml",
      "exec",
      "-T",
      "app",
      "sh",
      "-lc",
      "cat /var/lib/koda/state/control_plane/bootstrap.txt",
    ],
    { cwd: repoRoot(), encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
  );
  const match = output.match(/[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}/);
  if (!match) {
    throw new Error("Unable to read the local control-plane bootstrap code.");
  }
  return match[0];
}

export function installConsoleGuard(page: Page, options: ConsoleGuardOptions = {}): ConsoleIssue[] {
  const issues: ConsoleIssue[] = [];
  page.on("pageerror", (err) => issues.push({ type: "pageerror", text: String(err) }));
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    if (text.includes("Download the React DevTools")) return;
    if (options.allow?.some((pattern) => pattern.test(text))) return;
    issues.push({ type: "console", text });
  });
  return issues;
}

export async function disableProductTour(page: Page): Promise<void> {
  await page.addInitScript(() => {
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
}

export function expectNoConsoleIssues(issues: ConsoleIssue[]): void {
  expect(issues.map((issue) => `${issue.type}: ${issue.text}`)).toEqual([]);
}

export async function gotoHealthy(page: Page, pathname: string) {
  const response = await page.goto(pathname, { waitUntil: "domcontentloaded" });
  const status = response?.status() ?? 200;
  expect(status, `${pathname} responded with ${status}`).toBeLessThan(500);
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => undefined);
  await expect(page.locator("body")).not.toBeEmpty({ timeout: 15_000 });
  await expect(page.locator("text=/Application error|Internal Server Error|Unhandled Runtime Error/i")).toHaveCount(0);
  return response;
}

export async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  await expect
    .poll(
      () =>
        page.evaluate(() => {
          const root = document.documentElement;
          return root.scrollWidth <= root.clientWidth + 2;
        }),
      { timeout: 15_000 },
    )
    .toBe(true);
}

export async function expectNoStuckBusyState(page: Page): Promise<void> {
  await expect
    .poll(
      () =>
        page.evaluate(() =>
          Array.from(document.querySelectorAll("[aria-busy='true']")).filter((node) => {
            const element = node as HTMLElement;
            return element.offsetParent !== null;
          }).length,
        ),
      { timeout: 15_000 },
    )
    .toBe(0);
}

export async function attachCheckpoint(page: Page, testInfo: TestInfo, name: string): Promise<void> {
  const screenshot = await page.screenshot({ fullPage: true });
  await testInfo.attach(name, { body: screenshot, contentType: "image/png" });
}

export async function expectJsonOk(request: APIRequestContext, pathName: string): Promise<unknown> {
  const response = await request.get(pathName);
  expect(response.status(), pathName).toBeLessThan(500);
  expect(response.ok(), pathName).toBeTruthy();
  return response.json();
}

export function redactText(text: string): string {
  return text
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[email]")
    .replace(/(token|secret|password)["'=:\s]+[^\s"']+/gi, "$1=[redacted]");
}
