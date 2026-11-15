import { expect, test, type Locator, type Page } from "@playwright/test";

// D-330: text-[var(--font-size-*)] compiled to color:, so the size never applied;
// the classes now carry the length: hint. D-331: an unlayered
// `button, input, select, textarea { font: inherit }` beat every layered Tailwind
// font utility on those controls; it now sits in @layer base. jsdom has no
// cascade layers, so both are checked against the production build in Chromium.

async function signIn(page: Page): Promise<void> {
  const baseURL = test.info().project.use.baseURL ?? "";
  await page.context().addCookies([
    { name: "koda.tour.disabled", value: "1", url: baseURL },
    { name: "atlas.locale", value: "en-US", url: baseURL },
  ]);
  await page.addInitScript(() => {
    try {
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
      // Storage can be unavailable; the checks do not depend on it.
    }
  });
  await page.goto("/login");
  await page.locator("#login-identifier").fill("owner");
  await page.locator("#login-password").fill("stub-password-local-only");
  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith("/login")),
    page.locator('button[type="submit"]').click(),
  ]);
}

const fontSize = (locator: Locator) => locator.evaluate((element) => getComputedStyle(element).fontSize);

test("font-size tokens set the size on text (D-330)", async ({ page }) => {
  await signIn(page);
  await page.goto("/sessions");
  await page.getByRole("button", { name: "New conversation" }).first().click();
  await page.getByRole("button", { name: "Room", exact: true }).click();
  await page.getByRole("button", { name: /Set up a room/ }).click();
  const dialog = page.locator('[role="dialog"][aria-modal="true"]');
  // text-[length:var(--font-size-md)] and text-[length:var(--font-size-sm)]: 15px and 13px, not the inherited 14px.
  await expect(dialog.locator("#new-room-dialog-title")).toBeVisible();
  expect(await fontSize(dialog.locator("#new-room-dialog-title"))).toBe("15px");
  expect(await fontSize(dialog.locator("p").first())).toBe("13px");
});

test("a font utility on a control wins, and a control without one inherits (D-331)", async ({ page }) => {
  await signIn(page);
  await page.goto("/sessions");
  // The palette option is a <button> with text-[length:var(--font-size-sm)]: 13px, not the inherited 14px.
  await page.keyboard.press("Control+k");
  const option = page.getByRole("listbox").getByRole("option").first();
  await expect(option).toBeVisible();
  expect(await fontSize(option)).toBe("13px");
  await page.keyboard.press("Escape");

  const sizes = await page.evaluate(() => {
    const frame = document.createElement("div");
    frame.style.fontSize = "17px";
    frame.style.fontWeight = "600";
    frame.innerHTML =
      '<button id="sized" class="text-xs font-normal">a</button><button id="plain">b</button><input id="field" />';
    document.body.append(frame);
    const style = (id: string) => {
      const computed = getComputedStyle(document.getElementById(id) as HTMLElement);
      return `${computed.fontSize} ${computed.fontWeight}`;
    };
    const result = { sized: style("sized"), plain: style("plain"), field: style("field") };
    frame.remove();
    return result;
  });
  expect(sizes).toEqual({ sized: "12px 400", plain: "17px 600", field: "17px 600" });
});
