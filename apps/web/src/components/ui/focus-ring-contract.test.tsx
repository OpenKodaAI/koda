import { readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ts from "typescript";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { EffortPicker, type EffortCapability } from "@/components/control-plane/shared/effort-picker";
import { TagInputField } from "@/components/control-plane/shared/tag-input-field";
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

function sourceFiles(dir: string, pattern = /\.tsx$/): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(path, pattern);
    return pattern.test(entry.name) && !entry.name.includes(".test.") ? [path] : [];
  });
}

// Focus utilities that never paint on a control that is not a form field:
// the reset nulls its box-shadow (ring-*, shadow-*), and the unlayered global
// outline beats outline-none / outline-hidden.
const DEAD_FOCUS_UTILITY = /focus(?:-visible)?:(?:ring|shadow|outline-none|outline-hidden)[^\s"'`]*/g;
// Elements whose focus ring is drawn with box-shadow, which the reset spares.
const FIELD_ELEMENTS = new Set(["input", "textarea", "select", "Input", "Textarea"]);

/** The JSX element whose attribute holds `node`, if any. */
function owningElement(node: ts.Node): ts.JsxOpeningLikeElement | null {
  for (let current = node.parent; current; current = current.parent) {
    if (ts.isJsxAttribute(current)) {
      const element = current.parent.parent;
      return ts.isJsxOpeningElement(element) || ts.isJsxSelfClosingElement(element)
        ? element
        : null;
    }
    if (ts.isJsxElement(current) || ts.isJsxFragment(current) || ts.isFunctionLike(current)) {
      return null;
    }
  }
  return null;
}

function isFormField(element: ts.JsxOpeningLikeElement, source: ts.SourceFile): boolean {
  if (FIELD_ELEMENTS.has(element.tagName.getText(source))) return true;
  return element.attributes.properties.some(
    (attribute) => ts.isJsxAttribute(attribute) && attribute.name.getText(source) === "contentEditable",
  );
}

/** Every dead focus utility in class strings outside form fields, as `file:line utility`. */
function deadFocusUtilities(path: string, text = readFileSync(path, "utf8")): string[] {
  if (!text.match(DEAD_FOCUS_UTILITY)) return [];
  const source = ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const found: string[] = [];
  const visit = (node: ts.Node) => {
    const literal =
      ts.isStringLiteralLike(node) ||
      ts.isTemplateHead(node) ||
      ts.isTemplateMiddle(node) ||
      ts.isTemplateTail(node);
    if (literal) {
      const element = owningElement(node);
      if (!element || !isFormField(element, source)) {
        const { line } = source.getLineAndCharacterOfPosition(node.getStart(source));
        for (const [utility] of node.text.matchAll(DEAD_FOCUS_UTILITY)) {
          found.push(`${relative(SRC, path)}:${line + 1} ${utility}`);
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return found;
}

const DIM_UTILITY = /^opacity-(?:\d+|\[[^\]]+\])$/;

/**
 * Every element from the focused control up that an opacity utility dims
 * while focus is on the control. Opacity dims the outline or ring painted
 * inside it too, so the control returns to full opacity on
 * `focus-visible:opacity-100`, and a dimmed group around it on
 * `has-[:focus-visible]:opacity-100`.
 */
function dimmedOnFocus(focused: Element): string[] {
  const found: string[] = [];
  for (let element: Element | null = focused; element; element = element.parentElement) {
    const classes = (element.getAttribute("class") ?? "").split(/\s+/);
    const dim = classes.find((name) => DIM_UTILITY.test(name) && name !== "opacity-100");
    if (!dim) continue;
    const restore = element === focused ? "focus-visible:opacity-100" : "has-[:focus-visible]:opacity-100";
    if (!classes.includes(restore)) {
      const role = element.getAttribute("role");
      found.push(`${element.tagName.toLowerCase()}${role ? `[role=${role}]` : ""} is ${dim} without ${restore}`);
    }
  }
  return found;
}

/** Tabs through `container`, returning each element that took focus. */
async function tabStops(container: HTMLElement): Promise<HTMLElement[]> {
  const user = userEvent.setup();
  const stops: HTMLElement[] = [];
  for (;;) {
    await user.tab();
    const active = document.activeElement;
    if (!(active instanceof HTMLElement) || !container.contains(active) || stops.includes(active)) {
      return stops;
    }
    stops.push(active);
  }
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
// Checkboxes and radios are controls: they keep the global outline.
const NATIVE_TEXT_INPUT = 'input:not([type="checkbox"], [type="radio"])';
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
    expect([...fields]).toEqual([NATIVE_TEXT_INPUT, ...FORM_FIELDS.slice(1)]);
  });

  it("native checkboxes and radios keep the global outline", () => {
    // They are controls, not text fields: nothing else draws their ring.
    const removals = CSS_RULES.filter(({ body }) => /(^|[;\s])outline:\s*none/.test(body))
      .flatMap(({ selectors }) => selectors)
      .filter((selector) => /:focus(-visible)?$/.test(selector))
      .map((selector) => selector.replace(/:focus(-visible)?$/, ""));
    const host = document.createElement("div");
    host.innerHTML = '<input type="checkbox"><input type="radio"><input type="text">';
    document.body.append(host);
    try {
      const [checkbox, radio, text] = [...host.querySelectorAll("input")];
      const matching = (element: Element) =>
        removals.filter((selector) => element.matches(selector));
      expect(matching(checkbox)).toEqual([]);
      expect(matching(radio)).toEqual([]);
      expect(matching(text).length).toBeGreaterThan(0);
    } finally {
      host.remove();
    }
  });

  it("every focus outline is painted in --focus-ring", () => {
    // .action-button draws a near-white or near-black ring (12:1 and up).
    const allowed = new Map([
      [".action-button:focus-visible", "color-mix(in srgb, var(--text-primary) 90%, transparent)"],
    ]);
    const offenders = CSS_RULES.filter(({ selectors }) => selectors.some((s) => /:focus/.test(s)))
      .flatMap(({ selectors, body }) =>
        [...body.matchAll(/(?:^|[;\s])outline(?:-color)?:\s*([^;]+);/g)]
          .map(([, value]) => value.replace(/!important/, "").trim())
          .filter((value) => !/^(none|0)$/.test(value))
          .map((value) => value.replace(/^[\d.]+px\s+solid\s+/, ""))
          .filter((colour) => colour !== "var(--focus-ring)")
          .filter((colour) => !selectors.every((selector) => allowed.get(selector) === colour))
          .map((colour) => `${selectors.join(", ")} -> ${colour}`),
      );
    expect(offenders).toEqual([]);
  });

  it("no focus rule on a non-field control swaps the outline for a box-shadow the reset nulls", () => {
    // Classes only ever set on form fields: the reset spares them while
    // focused. .field-shell is not one of them: it also sits on buttons (the
    // ModelSelector trigger) and on wrappers.
    const formFieldClasses = [".auth-input.auth-input", ".bootstrap-code-input__cell"];
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

  it("TagInputField frames its bare input with a focus-within ring", () => {
    render(
      <I18nProvider initialLanguage="en-US">
        <TagInputField label="Tags" values={[]} onChange={() => {}} />
      </I18nProvider>,
    );
    const input = screen.getByRole("textbox");
    expect(input.className).toContain("outline-none");
    const wrapper = input.closest(".field-shell");
    expect(wrapper, "the tag field keeps its .field-shell frame").not.toBe(input);
    for (const required of [
      "focus-within:border-[color:var(--focus-ring)]",
      "focus-within:outline",
      "focus-within:outline-[color:var(--focus-ring)]",
    ]) {
      expect(wrapper?.className.split(/\s+/)).toContain(required);
    }
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

  it("no control outside a form field carries focus ring, shadow or outline-none utilities", () => {
    // They never paint (see DEAD_FOCUS_UTILITY), so they only mislead: a
    // copied focus-visible:ring-[var(--accent)] still shows the grey outline.
    const offenders = sourceFiles(SRC, /\.tsx?$/).flatMap((path) => deadFocusUtilities(path));
    expect(offenders).toEqual([]);
  });

  it("the dead-utility scan skips form fields and still sees class constants", () => {
    const probe = join(SRC, "components/ui/focus-probe.tsx");
    const fixture = [
      'const tab = "px-2 focus-visible:ring-2";',
      'export const A = () => <input className="focus-visible:ring-1" />;',
      'export const B = () => <div contentEditable className="focus:shadow-sm" />;',
      'export const C = () => <button className={cn("x", "focus-visible:outline-none")} />;',
      "export const D = () => <Link className={`a ${tab} focus:ring-[var(--accent)]`} />;",
    ].join("\n");
    expect(deadFocusUtilities(probe, fixture)).toEqual([
      "components/ui/focus-probe.tsx:1 focus-visible:ring-2",
      "components/ui/focus-probe.tsx:4 focus-visible:outline-none",
      "components/ui/focus-probe.tsx:5 focus:ring-[var(--accent)]",
    ]);
  });

  it("the toast sets --focus-ring to its own text colour, at full opacity on focus", async () => {
    function Probe() {
      const { showToast } = useToast();
      return (
        <button
          type="button"
          onClick={() =>
            showToast("Saved", "warning", {
              durationMs: 10_000,
              action: { label: "Undo", onClick: () => {} },
            })
          }
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
    expect(toast.style.getPropertyValue("--focus-ring")).toBe("var(--tone-warning-text)");

    // A dimmed button dims its own outline too (the dark warning ring falls
    // to 2.93:1 at 70%), so every dimmed control returns to full opacity
    // while it has keyboard focus.
    const controls = within(toast).getAllByRole("button");
    expect(controls).toHaveLength(2);
    for (const control of controls) {
      expect(dimmedOnFocus(control), control.textContent ?? "").toEqual([]);
    }
  });

  it("every range input draws its own 2px --focus-ring ring, with or without .ui-slider", () => {
    // The form-field rule removes a range input's outline, like any input's.
    const rings = CSS_RULES.filter(({ body }) =>
      /(?:^|[;\s])box-shadow:\s*0 0 0 2px var\(--focus-ring\)\s*;/.test(body),
    ).flatMap(({ selectors }) => selectors.filter((selector) => selector.endsWith(":focus-visible")));
    const host = document.createElement("div");
    host.innerHTML = '<input type="range">';
    document.body.append(host);
    try {
      const bare = host.querySelector("input") as HTMLInputElement;
      const matching = rings.filter((selector) => bare.matches(selector.replace(/:focus-visible$/, "")));
      expect(matching, "a ring rule that matches a range input with no class").not.toEqual([]);
    } finally {
      host.remove();
    }
  });

  it("no form-field ring uses the translucent --accent-muted", () => {
    const translucent = /focus(?:-visible|-within)?:(?:ring|border|outline)-\[(?:color:)?var\(--accent-muted\)\]/;
    const offenders = sourceFiles(SRC)
      .filter((path) => translucent.test(readFileSync(path, "utf8")))
      .map((path) => relative(SRC, path));
    expect(offenders).toEqual([]);
  });

  describe("a control dimmed while it inherits keeps a full-strength ring on focus", () => {
    const inheriting = (capability: EffortCapability) =>
      render(
        <I18nProvider initialLanguage="en-US">
          <EffortPicker
            capability={capability}
            value={null}
            inheritedValue={capability.kind === "enum" ? "medium" : 2000}
            onChange={() => {}}
            context="agent"
          />
        </I18nProvider>,
      ).container;

    it("EffortPicker effort tabs", async () => {
      const container = inheriting({ kind: "enum", values: ["low", "medium", "high"] });
      const stops = await tabStops(container);
      expect(stops.map((stop) => stop.getAttribute("role") ?? stop.tagName.toLowerCase())).toContain("tab");
      for (const stop of stops) {
        expect(dimmedOnFocus(stop), stop.textContent ?? "").toEqual([]);
      }
    });

    it("EffortPicker token slider and number field", async () => {
      const container = inheriting({ kind: "tokens", min: 0, max: 8000 });
      const stops = await tabStops(container);
      expect(stops.map((stop) => stop.getAttribute("type"))).toEqual(
        expect.arrayContaining(["range", "number"]),
      );
      for (const stop of stops) {
        expect(dimmedOnFocus(stop), stop.getAttribute("type") ?? "").toEqual([]);
      }
      const number = within(container).getByRole("spinbutton");
      expect(number.className).toContain("focus-visible:border-[var(--focus-ring)]");
      expect(number.className).toContain("focus-visible:ring-[var(--focus-ring)]");
    });

    it("the dimmed-focus check sees a dimmed ancestor and a dimmed control", () => {
      const host = document.createElement("div");
      host.innerHTML = [
        '<div class="opacity-60"><button class="a">a</button></div>',
        '<div class="opacity-60 has-[:focus-visible]:opacity-100"><button class="opacity-50">b</button></div>',
        '<div class="opacity-60 has-[:focus-visible]:opacity-100"><button class="opacity-50 focus-visible:opacity-100">c</button></div>',
      ].join("");
      const [a, b, c] = [...host.querySelectorAll("button")];
      expect(dimmedOnFocus(a)).toEqual(["div is opacity-60 without has-[:focus-visible]:opacity-100"]);
      expect(dimmedOnFocus(b)).toEqual(["button is opacity-50 without focus-visible:opacity-100"]);
      expect(dimmedOnFocus(c)).toEqual([]);
    });
  });
});
