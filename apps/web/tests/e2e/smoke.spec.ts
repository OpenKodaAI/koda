import { expect, test } from "@playwright/test";

/**
 * Smoke specs are tagged @smoke so they run on every PR; they require no
 * authenticated state and no Python backend. They exist to prove the
 * toolchain is wired correctly.
 */

test.describe("smoke @smoke", () => {
  test("public landing page renders without console errors", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(String(err)));
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });

    await page.goto("/");
    await expect(page).toHaveTitle(/koda/i);
    expect(errors).toHaveLength(0);
  });

  test("auth bootstrap page is reachable", async ({ page }) => {
    const response = await page.goto("/setup");
    // Either the page renders (200) or redirects to a known route.
    expect([200, 302, 307, 308]).toContain(response?.status() ?? 200);
  });
});
