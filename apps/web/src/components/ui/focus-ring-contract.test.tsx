import { readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { RailSearch } from "@/components/sessions/rail/rail-search";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ToastNotification } from "@/components/ui/toast-notification";
import { ToastProvider, useToast } from "@/hooks/use-toast";

// M8-E1-T1 (D-114, F-WEB-15, F-WEB-16): keyboard focus must be visible on
// every primitive in both themes. jsdom cannot paint, so this pins the CSS
// and class contract that makes the ring render; the browser pass checks the
// painted result.

const SRC = resolve(__dirname, "../..");

const css = readFileSync(resolve(SRC, "app/globals.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

const CSS_RULES = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(([, selector, body]) => ({
  selectors: selector
    .trim()
    .split(/,(?![^()]*\))/)
    .map((part) => part.trim()),
  body,
}));

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

type Rgba = [number, number, number, number];

function parseColor(value: string): Rgba {
  const hex = value.match(/^#([0-9a-fA-F]{6})$/);
  if (hex) {
    const digits = hex[1];
    const [r, g, b] = [0, 2, 4].map((offset) => parseInt(digits.slice(offset, offset + 2), 16));
    return [r, g, b, 1];
  }
  const rgba = value.match(
    /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)$/,
  );
  if (rgba) {
    const alpha = rgba[4] === undefined ? 1 : Number(rgba[4]);
    return [Number(rgba[1]), Number(rgba[2]), Number(rgba[3]), alpha];
  }
  throw new Error(`unsupported colour: ${value}`);
}

/** Paints `top` over an opaque `bottom`. */
function over(top: string, bottom: Rgba): Rgba {
  const [r, g, b, a] = parseColor(top);
  return [
    r * a + bottom[0] * (1 - a),
    g * a + bottom[1] * (1 - a),
    b * a + bottom[2] * (1 - a),
    1,
  ];
}

function luminance(color: string | Rgba): number {
  const [r, g, b] = (typeof color === "string" ? parseColor(color) : color)
    .slice(0, 3)
    .map((channel) => channel / 255)
    .map((channel) =>
      channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4,
    );
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string | Rgba, b: string | Rgba): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

function resolveToken(tokens: Record<string, string>, value: string): string {
  const reference = value.match(/^var\((--[\w-]+)\)$/);
  return reference ? resolveToken(tokens, tokens[reference[1]]) : value;
}

function ruleBody(selector: string): string {
  const rule = CSS_RULES.find((candidate) => candidate.selectors.includes(selector));
  if (!rule) throw new Error(`rule not found: ${selector}`);
  return rule.body;
}

function declaration(body: string, property: string): string {
  const match = body.match(new RegExp(`(?:^|[;\\s])${property}:\\s*([^;]+);`));
  if (!match) throw new Error(`${property} not declared`);
  return match[1].trim();
}

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return entry.name.endsWith(".tsx") && !entry.name.includes(".test.") ? [path] : [];
  });
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

const TONES = ["success", "danger", "warning", "info"] as const;

const THEMES = {
  light: {
    tokens: tokenBlock(/^:root \{/m),
    tourPane: ':where(html[data-theme="light"]) .tour-layer__pane',
  },
  "dark (system preference)": {
    tokens: tokenBlock(/^\s*:root:not\(\[data-theme="light"\]\) \{/m),
    tourPane: ".tour-layer__pane",
  },
  "dark (explicit)": {
    tokens: tokenBlock(/^html\[data-theme="dark"\],\s*html\.dark \{/m),
    tourPane: ".tour-layer__pane",
  },
};

// The global rule removes the outline from these form fields, and the
// flat-design reset must spare exactly them while they hold focus.
const FORM_FIELDS = ["input", "textarea", "select", '[contenteditable="true"]'];
const RESET_ELEMENT_SELECTOR = `html body *:where(:not(:is(${FORM_FIELDS.join(", ")}):focus-visible))`;

const PAINTED_BOX_SHADOW = /box-shadow:\s*(?!none)[^;]+;/;

describe("focus ring contract (M8-E1-T1)", () => {
  for (const [theme, { tokens, tourPane }] of Object.entries(THEMES)) {
    it(`--focus-ring has at least 3:1 contrast on every ${theme} surface and on the accent fill`, () => {
      const ring = tokens["--focus-ring"];
      expect(ring, `${theme} defines --focus-ring`).toMatch(/^#[0-9a-fA-F]{6}$/);
      expect(tokens["--accent"], `${theme} defines --accent`).toBeDefined();
      for (const surface of [...SURFACES, "--accent"]) {
        const background = tokens[surface];
        if (!background) continue;
        expect(
          contrast(ring, background),
          `${theme}: --focus-ring ${ring} on ${surface} ${background}`,
        ).toBeGreaterThanOrEqual(3);
      }
    });

    it(`the toast ring (its text colour) keeps 3:1 on every ${theme} tone fill`, () => {
      for (const tone of TONES) {
        const fill = tokens[`--tone-${tone}-bg-strong`];
        const text = tokens[`--tone-${tone}-text`];
        expect(contrast(text, fill), `${theme} ${tone}: ${text} on ${fill}`).toBeGreaterThanOrEqual(3);
      }
    });

    it(`the tour coachmark ring keeps 3:1 on its ${theme} glass card`, () => {
      const ring = resolveToken(tokens, declaration(ruleBody(".tour-coachmark"), "--focus-ring"));
      const dimmed = over(
        declaration(ruleBody(tourPane), "background"),
        parseColor(tokens["--canvas"]),
      );
      for (const glass of ["--overlay-floating-bg", "--overlay-modal-bg"]) {
        const card = over(tokens[glass], dimmed);
        expect(
          contrast(ring, card),
          `${theme}: ${ring} on ${glass} over the tour layer`,
        ).toBeGreaterThanOrEqual(3);
      }
    });
  }

  it("the flat-design reset spares only focused form fields, at its original specificity", () => {
    const resets = CSS_RULES.filter(
      ({ selectors, body }) =>
        selectors.some((selector) => selector.startsWith("html body *")) &&
        /box-shadow:\s*none\s*!important/.test(body),
    );
    expect(resets).toHaveLength(1);
    expect(resets[0].selectors).toEqual([
      RESET_ELEMENT_SELECTOR,
      "html body *::before",
      "html body *::after",
    ]);

    const outlineRemoval = CSS_RULES.find(
      ({ selectors, body }) =>
        selectors.every((selector) => selector.startsWith("html body ")) &&
        /outline:\s*none\s*!important/.test(body),
    );
    const fields = new Set(
      outlineRemoval?.selectors.map((selector) =>
        selector.replace(/^html body /, "").replace(/:focus(-visible)?$/, ""),
      ),
    );
    expect([...fields]).toEqual(FORM_FIELDS);
  });

  it("no focus rule on a non-field control swaps the outline for a box-shadow the reset nulls", () => {
    // Form-field classes: the reset spares them while focused.
    const formFieldClasses = [".field-shell", ".auth-input.auth-input", ".bootstrap-code-input__cell"];
    const offenders = CSS_RULES.filter(({ body }) => /(^|[;\s])outline:\s*(none|0)\s*;/.test(body))
      .filter(({ body }) => PAINTED_BOX_SHADOW.test(body))
      .flatMap(({ selectors }) => selectors)
      .filter((selector) => /:focus/.test(selector))
      .filter((selector) => !formFieldClasses.some((field) => selector.startsWith(field)));
    expect(offenders).toEqual([]);
  });

  it("no wrapper draws focus-within with a box-shadow, which the reset nulls", () => {
    const inComponents = sourceFiles(SRC)
      .filter((path) => /focus-within:(shadow|ring)-/.test(readFileSync(path, "utf8")))
      .map((path) => relative(SRC, path));
    expect(inComponents).toEqual([]);

    const inCss = CSS_RULES.filter(({ body }) => PAINTED_BOX_SHADOW.test(body))
      .flatMap(({ selectors }) => selectors)
      .filter((selector) => selector.includes(":focus-within"));
    expect(inCss).toEqual([]);
  });

  it("a field wrapper draws a --focus-ring border and outline on focus-within", () => {
    render(
      <I18nProvider initialLanguage="en-US">
        <RailSearch value="" onChange={() => {}} />
      </I18nProvider>,
    );
    const wrapper = screen.getByRole("searchbox").closest("label");
    expect(wrapper?.className).toContain("focus-within:border-[color:var(--focus-ring)]");
    expect(wrapper?.className).toContain("focus-within:outline-[color:var(--focus-ring)]");
  });

  it("Input and Textarea paint a --focus-ring border and ring on focus", () => {
    render(
      <>
        <Input aria-label="input" />
        <Textarea aria-label="textarea" />
      </>,
    );
    for (const element of [screen.getByLabelText("input"), screen.getByLabelText("textarea")]) {
      expect(element.className).toContain("focus-visible:border-[var(--focus-ring)]");
      expect(element.className).toContain("focus-visible:ring-[var(--focus-ring)]");
    }
  });

  it("Button and the Select trigger rely on the global outline, not a second ring", () => {
    render(
      <>
        <Button mode="input">input mode</Button>
        <Button>default mode</Button>
        <Button mode="icon" aria-label="icon mode" />
        <Select>
          <SelectTrigger aria-label="select">
            <SelectValue placeholder="pick" />
          </SelectTrigger>
        </Select>
      </>,
    );
    for (const element of [
      screen.getByRole("button", { name: "input mode" }),
      screen.getByRole("button", { name: "default mode" }),
      screen.getByRole("button", { name: "icon mode" }),
      screen.getByRole("combobox", { name: "select" }),
    ]) {
      expect(element.className).not.toMatch(
        /focus(-visible)?:(ring|shadow|outline-none|outline-hidden)/,
      );
    }
  });

  it("the toast sets --focus-ring to its own text colour", async () => {
    function Probe() {
      const { showToast } = useToast();
      return (
        <button
          type="button"
          onClick={() => showToast("Saved", "success", { durationMs: 10_000 })}
        >
          Show toast
        </button>
      );
    }
    render(
      <I18nProvider initialLanguage="en-US">
        <ToastProvider>
          <Probe />
          <ToastNotification />
        </ToastProvider>
      </I18nProvider>,
    );
    await userEvent.setup().click(screen.getByRole("button", { name: "Show toast" }));
    const toast = await screen.findByRole("status");
    expect(toast.style.getPropertyValue("--focus-ring")).toBe("var(--tone-success-text)");
  });
});
