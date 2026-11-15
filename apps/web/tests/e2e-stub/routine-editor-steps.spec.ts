import { expect, test, type Locator, type Page } from "@playwright/test";

// D-268: the editor's Next (type=button) and Create/Save (type=submit) buttons used to share
// one footer slot, so React reused the DOM button and flipped its type during the click.
// Chromium then submitted the form from Next on the Schedule step. jsdom does not reproduce
// this, so the check runs against the production build in a real browser.

async function prepareContext(page: Page): Promise<void> {
  const baseURL = test.info().project.use.baseURL ?? "";
  await page.context().addCookies([
    { name: "koda.tour.disabled", value: "1", url: baseURL },
    { name: "atlas.locale", value: "en-US", url: baseURL },
  ]);
  await page.addInitScript(() => {
    try {
      window.localStorage.setItem("atlas.locale", JSON.stringify("en-US"));
      window.localStorage.setItem(
        "ui:onboarding-tour",
        JSON.stringify({
          version: 2,
          status: "skipped",
          currentStepId: null,
          completedChapters: [],
          updatedAt: 1,
          completedAt: null,
          skippedAt: 1,
        }),
      );
    } catch {
      // Storage can be unavailable; the stub flow does not depend on it.
    }
  });
}

async function signIn(page: Page): Promise<void> {
  await page.goto("/login");
  await page.locator("#login-identifier").fill("owner");
  await page.locator("#login-password").fill("stub-password-local-only");
  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith("/login")),
    page.locator('button[type="submit"]').click(),
  ]);
}

// Every non-GET request to a schedules route: creating, saving or deleting a routine.
function recordScheduleWrites(page: Page): string[] {
  const writes: string[] = [];
  page.on("request", (request) => {
    const { pathname } = new URL(request.url());
    if (request.method() !== "GET" && pathname.includes("/schedules")) {
      writes.push(`${request.method()} ${pathname}`);
    }
  });
  return writes;
}

async function openRoutines(page: Page): Promise<string[]> {
  await prepareContext(page);
  await signIn(page);
  const writes = recordScheduleWrites(page);
  await page.goto("/routines/schedules");
  await expect(page.getByText("Check deploy health").first()).toBeVisible({ timeout: 30_000 });
  return writes;
}

async function expectStep(dialog: Locator, label: "Basics" | "Schedule" | "Refine"): Promise<void> {
  await expect(dialog.locator("header").getByText(label, { exact: true })).toBeVisible();
}

// Clicking Next on the Schedule step must only move to Refine. A form submission would send
// a request and, once it succeeds, close the editor, so both are checked after a short settle.
// Next unmounts there, so the submit button must take focus instead of the page body.
async function nextFromScheduleReachesRefine(page: Page, dialog: Locator, writes: string[]) {
  await expectStep(dialog, "Schedule");
  await dialog.getByRole("button", { name: "Next" }).click();
  await expectStep(dialog, "Refine");
  await page.waitForTimeout(750);
  expect(writes).toEqual([]);
  await expect(dialog).toBeVisible();
  await expectStep(dialog, "Refine");
}

test("create: Next on the Schedule step reaches Refine without creating the routine", async ({ page }) => {
  const writes = await openRoutines(page);

  await page.getByRole("button", { name: "New routine" }).first().click();
  const dialog = page.getByRole("dialog");
  await expectStep(dialog, "Basics");
  await dialog.getByPlaceholder("e.g., Daily code review").fill("Nightly digest");
  await dialog.getByPlaceholder("Describe what the agent should do on each run").fill("Summarize the day");
  await dialog.getByRole("button", { name: "Next" }).click();

  await nextFromScheduleReachesRefine(page, dialog, writes);
  await expect(dialog.getByRole("button", { name: "Create routine" })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Create routine" })).toBeFocused();
  await expect(dialog.getByRole("button", { name: "Next" })).toHaveCount(0);
  expect(writes).toEqual([]);
});

test("edit: Next on the Schedule step reaches Refine and the Delete button without saving", async ({ page }) => {
  const writes = await openRoutines(page);

  await page.getByRole("button", { name: "Edit" }).first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Edit routine #7")).toBeVisible();
  await expectStep(dialog, "Basics");
  await dialog.getByRole("button", { name: "Next" }).click();

  await nextFromScheduleReachesRefine(page, dialog, writes);
  await expect(dialog.getByRole("button", { name: "Delete routine" })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Save changes" })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Save changes" })).toBeFocused();
  expect(writes).toEqual([]);
});

// Basics and Schedule have no submit button, so Enter in the name field triggers the form's
// implicit submission. It must only advance to Schedule and keep focus inside the dialog;
// a submission would create the routine early or save and close the editor.
async function enterInNameAdvancesToSchedule(page: Page, dialog: Locator, writes: string[]) {
  await dialog.getByPlaceholder("e.g., Daily code review").press("Enter");
  await expectStep(dialog, "Schedule");
  await page.waitForTimeout(750);
  expect(writes).toEqual([]);
  await expect(dialog).toBeVisible();
  await expectStep(dialog, "Schedule");
  await expect(dialog.getByRole("button", { name: "Next" })).toBeFocused();
}

test("create: Enter in the name field on Basics moves to Schedule without creating the routine", async ({
  page,
}) => {
  const writes = await openRoutines(page);

  await page.getByRole("button", { name: "New routine" }).first().click();
  const dialog = page.getByRole("dialog");
  await expectStep(dialog, "Basics");
  await dialog.getByPlaceholder("Describe what the agent should do on each run").fill("Summarize the day");
  await dialog.getByPlaceholder("e.g., Daily code review").fill("Nightly digest");

  await enterInNameAdvancesToSchedule(page, dialog, writes);
});

test("edit: Enter in the name field on Basics moves to Schedule without saving", async ({ page }) => {
  const writes = await openRoutines(page);

  await page.getByRole("button", { name: "Edit" }).first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Edit routine #7")).toBeVisible();
  await expectStep(dialog, "Basics");

  await enterInNameAdvancesToSchedule(page, dialog, writes);
  await dialog.getByRole("button", { name: "Next" }).click();
  await expectStep(dialog, "Refine");
  await expect(dialog.getByRole("button", { name: "Delete routine" })).toBeVisible();
  expect(writes).toEqual([]);
});

// Schedule has no submit button either. In edit mode the interval field is its only text input,
// so Enter there must only advance to Refine, never save and close before Refine and Delete.
test("edit: Enter in the interval field on Schedule moves to Refine without saving", async ({ page }) => {
  const writes = await openRoutines(page);

  await page.getByRole("button", { name: "Edit" }).first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Edit routine #7")).toBeVisible();
  await dialog.getByRole("button", { name: "Next" }).click();
  await expectStep(dialog, "Schedule");

  await dialog.getByRole("textbox", { name: /^Every/ }).press("Enter");
  await expectStep(dialog, "Refine");
  await page.waitForTimeout(750);
  expect(writes).toEqual([]);
  await expect(dialog).toBeVisible();
  await expectStep(dialog, "Refine");
  await expect(dialog.getByRole("button", { name: "Delete routine" })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Save changes" })).toBeFocused();
});
