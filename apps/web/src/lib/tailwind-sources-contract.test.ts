// @vitest-environment node
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// D-351: Tailwind scanned the test files too, so a probe class that only a
// test spells (token-reference-contract.test.ts writes text-[var(--font-size-sm)]
// to prove the lint catches it) became a real rule in the shipped CSS:
// .text-[var(--font-size-sm)]{color:var(--font-size-sm)}. apps/web/CLAUDE.md
// spells the same class as the example of what not to write. globals.css
// excludes test and spec files and the Markdown guides from the sources; this
// compiles it the way the Next build does (the @tailwindcss/postcss plugin,
// scanning from apps/web) and reads the CSS.

const WEB_ROOT = resolve(__dirname, "../..");
const GLOBALS = resolve(WEB_ROOT, "src/app/globals.css");
// Spelled only here, in a test file: the scan must not see it.
const PROBE_ONLY_IN_A_TEST = "mt-[4321px]";

async function buildCss(): Promise<string> {
  const require = createRequire(import.meta.url);
  const pluginPath = require.resolve("@tailwindcss/postcss");
  const postcss = createRequire(pluginPath)("postcss") as typeof import("postcss");
  const tailwind = require(pluginPath) as (options: { base: string; optimize: boolean }) => import("postcss").AcceptedPlugin;
  const result = await postcss([tailwind({ base: WEB_ROOT, optimize: false })]).process(readFileSync(GLOBALS, "utf8"), {
    from: GLOBALS,
  });
  return result.css;
}

describe("Tailwind sources (D-351)", () => {
  it("emits no utility for a class that only a test, spec or guide spells", async () => {
    const css = await buildCss();
    // The scan works: a utility the components use is there.
    expect(css.includes(".text-\\[length\\:var\\(--font-size-sm\\)\\]")).toBe(true);
    const testOnly = [
      `.${PROBE_ONLY_IN_A_TEST.replace(/[[\]()]/g, "\\$&")}`,
      // The token lint's probe, which only its test and the guide write.
      ".text-\\[var\\(--font-size-sm\\)\\]",
    ];
    expect(testOnly.filter((selector) => css.includes(selector))).toEqual([]);
  }, 60_000);
});
