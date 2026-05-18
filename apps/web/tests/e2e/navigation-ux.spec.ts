import { expect, test } from "@playwright/test";
import {
  attachCheckpoint,
  expectNoConsoleIssues,
  expectNoHorizontalOverflow,
  gotoHealthy,
  installConsoleGuard,
} from "./helpers/koda-e2e";

const primaryRoutes = [
  { path: "/", label: /home|koda|dashboard/i, checkpoint: "home" },
  { path: "/sessions", label: /sessions|sessões|sesiones/i },
  { path: "/runtime", label: /runtime/i, checkpoint: "runtime-overview" },
  { path: "/executions", label: /executions|execuções|ejecuciones/i, checkpoint: "executions" },
  { path: "/executions/dlq", label: /DLQ|dead letter|retries|execuções/i },
  { path: "/evaluations", label: /evals|evaluations|avaliações/i, checkpoint: "evals" },
  { path: "/costs", label: /costs|custos|costes/i },
  { path: "/memory", label: /memory|memória|memoria/i },
  { path: "/control-plane", label: /control plane|agents|agentes/i },
  { path: "/control-plane/system", label: /system|sistema|settings/i },
  { path: "/routines/schedules", label: /routines|rotinas|rutinas|schedule|agenda/i },
];

test.describe("navigation and UX guards", () => {
  for (const route of primaryRoutes) {
    test(`route ${route.path} has no 5xx, console errors or desktop overflow`, async ({ page }, testInfo) => {
      const consoleIssues = installConsoleGuard(page);
      await gotoHealthy(page, route.path);
      await expect(page.locator("body")).toContainText(route.label, { timeout: 15_000 });
      await expectNoHorizontalOverflow(page);
      if (route.checkpoint) await attachCheckpoint(page, testInfo, route.checkpoint);
      expectNoConsoleIssues(consoleIssues);
    });
  }

  test("primary routes avoid horizontal overflow on a mobile viewport", async ({ page }, testInfo) => {
    const consoleIssues = installConsoleGuard(page);
    await page.setViewportSize({ width: 390, height: 844 });
    for (const route of primaryRoutes.slice(0, 8)) {
      await gotoHealthy(page, route.path);
      await expectNoHorizontalOverflow(page);
    }
    await attachCheckpoint(page, testInfo, "mobile-navigation");
    expectNoConsoleIssues(consoleIssues);
  });
});
