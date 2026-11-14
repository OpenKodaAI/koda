import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

// M8-E1-T1 (D-114, F-WEB-15, F-WEB-16): keyboard focus must be visible on
// every primitive in both themes. jsdom cannot paint, so this pins the CSS
// and class contract that makes the ring render; the browser pass checks the
// painted result.

const css = readFileSync(resolve(__dirname, "../../app/globals.css"), "utf8").replace(
  /\/\*[\s\S]*?\*\//g,
  "",
);

function tokenBlock(selectorPattern: RegExp): Record<string, string> {
  const match = css.match(selectorPattern);
  if (!match || match.index === undefined) {
    throw new Error(`theme block not found: ${selectorPattern}`);
  }
  const start = css.indexOf("{", match.index) + 1;
  const end = css.indexOf("}", start);
  const tokens: Record<string, string> = {};
  for (const [, name, value] of css.slice(start, end).matchAll(/(--[\w-]+):\s*([^;]+);/g)) {
    tokens[name] = value.trim();
  }
  return tokens;
}

function luminance(hex: string): number {
  const value = hex.replace("#", "");
  const channels = [0, 2, 4].map((offset) => parseInt(value.slice(offset, offset + 2), 16) / 255);
  const [r, g, b] = channels.map((channel) =>
    channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// Every surface a focused control can sit on.
const SURFACES = [
  "--canvas",
  "--shell",
  "--sidebar-surface",
  "--panel",
  "--panel-soft",
  "--panel-strong",
  "--surface-hover",
  "--surface-hover-strong",
  "--surface-tint",
  "--surface-tint-strong",
  "--surface-elevated",
  "--surface-elevated-soft",
] as const;

const THEMES = {
  light: tokenBlock(/^:root \{/m),
  "dark (system preference)": tokenBlock(/^\s*:root:not\(\[data-theme="light"\]\) \{/m),
  "dark (explicit)": tokenBlock(/^html\[data-theme="dark"\],\s*html\.dark \{/m),
};

describe("focus ring contract (M8-E1-T1)", () => {
  for (const [theme, tokens] of Object.entries(THEMES)) {
    it(`--focus-ring has at least 3:1 contrast on every ${theme} surface`, () => {
      const ring = tokens["--focus-ring"];
      expect(ring, `${theme} defines --focus-ring`).toMatch(/^#[0-9a-fA-F]{6}$/);
      for (const surface of SURFACES) {
        const background = tokens[surface];
        if (!background) continue;
        expect(
          contrast(ring, background),
          `${theme}: --focus-ring ${ring} on ${surface} ${background}`,
        ).toBeGreaterThanOrEqual(3);
      }
    });
  }

  it("the flat-design box-shadow reset spares the focused element", () => {
    const rules = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter(
      ([, selector, body]) =>
        /html body \*/.test(selector) && /box-shadow:\s*none\s*!important/.test(body),
    );
    expect(rules.length).toBeGreaterThan(0);
    for (const [, selectorList] of rules) {
      for (const selector of selectorList.split(",").map((part) => part.trim())) {
        if (/::(before|after)$/.test(selector)) continue;
        expect(selector, "element selector of the box-shadow reset").toContain(
          ":not(:focus-visible)",
        );
      }
    }
  });

  it("text-entry primitives paint a --focus-ring border and ring on focus", () => {
    render(
      <>
        <Input aria-label="input" />
        <Textarea aria-label="textarea" />
        <Select>
          <SelectTrigger aria-label="select">
            <SelectValue placeholder="pick" />
          </SelectTrigger>
        </Select>
      </>,
    );
    for (const element of [
      screen.getByLabelText("input"),
      screen.getByLabelText("textarea"),
      screen.getByRole("combobox", { name: "select" }),
    ]) {
      expect(element.className).toContain("focus-visible:border-[var(--focus-ring)]");
      expect(element.className).toContain("focus-visible:ring-[var(--focus-ring)]");
    }
  });

  it("no Button mode uses the translucent accent-muted focus ring", () => {
    render(
      <>
        <Button mode="input">input mode</Button>
        <Button>default mode</Button>
      </>,
    );
    for (const name of ["input mode", "default mode"]) {
      const className = screen.getByRole("button", { name }).className;
      expect(className).not.toContain("ring-[var(--accent-muted)]");
      expect(className).toContain("focus-visible:ring-[var(--focus-ring)]");
    }
  });
});
