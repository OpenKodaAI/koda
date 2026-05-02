import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const CSS_PATH = resolve(__dirname, "../app/globals.css");
const css = readFileSync(CSS_PATH, "utf8");

function ruleBlock(selector: string): string {
  // Match `<selector> { ... }` allowing the selector to be one item in a
  // grouped selector list. We grab the body of whichever rule contains it.
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(
    `(?:^|,|\\s)\\s*${escaped}\\s*(?:,[^{]*)?\\{([^}]*)\\}`,
    "m",
  );
  const match = css.match(re);
  if (!match) {
    throw new Error(`Could not find CSS rule for "${selector}"`);
  }
  return match[1];
}

const CANONICAL = [
  ".app-overlay-backdrop",
  ".app-modal-panel",
  ".app-drawer-panel",
  ".app-floating-panel",
  ".app-floating-surface",
] as const;

describe("glass-blur contract (apps/web/src/app/globals.css)", () => {
  for (const selector of CANONICAL) {
    it(`${selector} declares backdrop-filter with !important`, () => {
      const body = ruleBlock(selector);
      expect(body).toMatch(/backdrop-filter:\s*var\([^)]+\)\s*!important/);
      expect(body).toMatch(
        /-webkit-backdrop-filter:\s*var\([^)]+\)\s*!important/,
      );
    });
  }

  it("never combines --transition-base with an explicit easing token", () => {
    // `--transition-base` is the shorthand "200ms cubic-bezier(...)", so
    // adding another easing token produces an invalid `transition`
    // declaration that the browser silently discards. The visible symptom
    // is that modals/drawers/popovers open abruptly with no animation.
    const offenders = css.match(
      /transition:[^;]*var\(--transition-base\)\s+var\(--ease[^)]+\)/g,
    );
    expect(offenders, "found broken transition shorthand").toBeNull();
  });

  it("uses @keyframes animation for every overlay animation class", () => {
    // Keyframe-based (not transition-based) is required so the enter
    // animation fires deterministically when the element mounts. A
    // transition would silently no-op if React batches the presence
    // helper's state flip into the same paint frame.
    for (const selector of [
      ".app-overlay-anim",
      ".app-modal-anim",
      ".app-drawer-anim-right",
      ".app-drawer-anim-left",
    ]) {
      const body = ruleBlock(selector);
      expect(body).toMatch(/animation:\s*app-[a-z-]+-enter\s+\d+ms/);
    }
    // Each must also declare an exit animation when [data-visible="false"].
    for (const selector of [
      '.app-overlay-anim[data-visible="false"]',
      '.app-modal-anim[data-visible="false"]',
      '.app-drawer-anim-right[data-visible="false"]',
      '.app-drawer-anim-left[data-visible="false"]',
    ]) {
      const body = ruleBlock(selector);
      expect(body).toMatch(/animation:\s*app-[a-z-]+-exit\s+\d+ms/);
    }
  });

  it("does not strip backdrop-filter from canonical panel surfaces", () => {
    // Any rule that targets a canonical panel selector (not its `::before`
    // sheen, not a `--compact` trigger button variant) and sets
    // backdrop-filter:none would silently break the glass contract.
    const noneRules = css.match(
      /([^{}]+)\{[^}]*backdrop-filter:\s*none[^}]*\}/g,
    );
    if (!noneRules) return;

    for (const block of noneRules) {
      const selectorPart = block.split("{")[0];
      for (const canonical of CANONICAL) {
        // Allow `::before` (sheen pseudo-elements) and selectors that
        // descend INTO a panel via a child combinator (rare overrides for
        // sub-elements), but forbid the bare panel selector.
        const bareMatch = new RegExp(
          `${canonical.replace(/\./g, "\\.")}\\s*(?:,|\\{|$)`,
        );
        if (bareMatch.test(selectorPart)) {
          throw new Error(
            `Found backdrop-filter:none rule that targets bare ${canonical}: ${selectorPart.trim()}`,
          );
        }
      }
    }
  });
});
