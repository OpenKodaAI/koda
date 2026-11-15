import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// D-331: unlayered CSS beats every layered rule, whatever its specificity, so
// an unlayered `button, input, select, textarea { font: inherit }` silently
// beat every Tailwind font utility (text-*, font-*, leading-*) on those
// elements: the palette option's text-[length:var(--font-size-sm)] rendered at
// the inherited 14px. A font rule on a bare control selector belongs in
// @layer base, where utilities win and an unstyled control still inherits.

const CSS = readFileSync(resolve(__dirname, "../app/globals.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

type Rule = { selector: string; body: string; layers: string[]; atRules: string[] };

/** Every style rule with the at-rule preludes that enclose it. */
function rules(css: string): Rule[] {
  const out: Rule[] = [];
  const stack: string[] = [];
  let start = 0;
  for (let index = 0; index < css.length; index += 1) {
    const char = css[index];
    if (char === "{") {
      const prelude = css.slice(start, index).trim().split(/[;}]/).pop()?.trim() ?? "";
      if (prelude.startsWith("@")) {
        stack.push(prelude);
        start = index + 1;
        continue;
      }
      const end = css.indexOf("}", index);
      out.push({
        selector: prelude,
        body: css.slice(index + 1, end),
        layers: stack.filter((at) => at.startsWith("@layer")),
        atRules: [...stack],
      });
      index = end;
      start = end + 1;
    } else if (char === "}") {
      stack.pop();
      start = index + 1;
    }
  }
  return out;
}

const CONTROL = /^(?:button|input|select|textarea)/;
const PSEUDO_SUFFIX = /^(?:\[[^\]]*\]|::?[\w-]+(?:\([^)]*\))?)*$/;
const FONT_DECLARATION = /(?:^|[;{\s])(font|font-size|font-weight|font-family|line-height)\s*:/;

/** The parts of a selector list, split on the commas outside parentheses. */
function selectorParts(selector: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let start = 0;
  for (let index = 0; index < selector.length; index += 1) {
    if (selector[index] === "(") depth += 1;
    else if (selector[index] === ")") depth -= 1;
    else if (selector[index] === "," && depth === 0) {
      parts.push(selector.slice(start, index).trim());
      start = index + 1;
    }
  }
  return [...parts, selector.slice(start).trim()];
}

/** A bare control selector, also inside :where() or :is(), which change specificity but not the layer. */
function isBareControl(part: string): boolean {
  const element = CONTROL.exec(part);
  if (element) return PSEUDO_SUFFIX.test(part.slice(element[0].length));
  const wrapper = /^:(?:where|is)\(/.exec(part);
  if (!wrapper) return false;
  let depth = 1;
  let index = wrapper[0].length;
  for (; index < part.length && depth > 0; index += 1) {
    if (part[index] === "(") depth += 1;
    else if (part[index] === ")") depth -= 1;
  }
  const inner = part.slice(wrapper[0].length, index - 1);
  return PSEUDO_SUFFIX.test(part.slice(index)) && selectorParts(inner).some(isBareControl);
}

/**
 * Unlayered rules that set a font property on every control of a kind (a bare
 * button, input, select or textarea selector, also wrapped in :where() or
 * :is()). A component rule scoped by a class (.agent-board-search input)
 * styles its own field and is not a reset.
 */
function unlayeredControlFonts(css: string): string[] {
  return rules(css)
    .filter(({ layers }) => layers.length === 0)
    .filter(({ body }) => FONT_DECLARATION.test(body))
    .filter(({ selector }) => selectorParts(selector).some(isBareControl))
    .map(({ selector }) => selector.replace(/\s+/g, " "));
}

describe("form control fonts (D-331)", () => {
  it("sets no font on a bare button, input, select or textarea outside a layer", () => {
    expect(unlayeredControlFonts(CSS)).toEqual([]);
    const inherit = rules(CSS).find(
      ({ selector, body }) => /\bbutton\b/.test(selector) && /font:\s*inherit/.test(body),
    );
    expect(inherit?.layers).toEqual(["@layer base"]);
  });

  it("the scan flags unlayered control fonts and passes layered or class-scoped ones", () => {
    const css = [
      "button, input { font: inherit; }",
      "@media (min-width: 1px) { textarea:focus-visible { font-size: 2px; } }",
      "@layer base { select { font: inherit; } }",
      ".composer textarea { font-size: 3px; }",
      "button:disabled { cursor: not-allowed; }",
      // :where() and :is() do not put a rule in a layer: unlayered, it still
      // beats every utility, whatever its specificity.
      ":where(button) { font: inherit; }",
      ":is(input):focus-visible { font-size: 2px; }",
      ":where(button, input, select, textarea) { font: inherit; }",
      ":where(.composer textarea) { font-size: 3px; }",
      "@layer base { :where(select) { font: inherit; } }",
    ].join("\n");
    expect(unlayeredControlFonts(css)).toEqual([
      "button, input",
      "textarea:focus-visible",
      ":where(button)",
      ":is(input):focus-visible",
      ":where(button, input, select, textarea)",
    ]);
  });
});

// D-349: the same mechanism as D-331 beyond fonts. Unlayered element rules beat every
// layered Tailwind utility on the elements they match: `a { color: inherit }` overrode
// every colour and decoration utility on links (the Home recents rendered in
// --text-primary under text-[color:var(--text-secondary)]), `button { cursor: pointer }`
// overrode cursor-* and disabled:cursor-not-allowed, and `button:active { opacity: .85 }`
// every opacity utility while pressed. An element-level rule sits in @layer base.
//
// Element level: no class and no id, only type selectors, *, attributes, pseudo-classes,
// pseudo-elements and combinators, also inside :where(), :is() and :not(). Allowed
// unlayered: custom properties (tokens), !important declarations (deliberate overrides
// such as the flat-design reset and reduced motion), and the focus indicator, which is
// unlayered on purpose so outline-none cannot remove it (M8-E1-T1): outline,
// outline-offset or box-shadow on a :focus or :focus-visible selector.

const FOCUS_PROPERTIES = new Set(["outline", "outline-offset", "box-shadow"]);

function isElementLevel(part: string): boolean {
  return !/[.#]/.test(part.replace(/\[[^\]]*\]/g, ""));
}

function declarations(body: string): { property: string; important: boolean }[] {
  return body
    .split(";")
    .map((declaration) => declaration.trim())
    .filter((declaration) => declaration.includes(":"))
    .map((declaration) => ({
      property: declaration.slice(0, declaration.indexOf(":")).trim().toLowerCase(),
      important: /!important\s*$/.test(declaration),
    }));
}

/** Unlayered element-level rules, as "selector { property }", that would beat a utility. */
function unlayeredElementRules(css: string): string[] {
  const out: string[] = [];
  for (const { selector, body, layers, atRules } of rules(css)) {
    if (layers.length > 0 || atRules.some((at) => /^@(?:-webkit-)?keyframes\b/.test(at))) continue;
    const parts = selectorParts(selector);
    if (!parts.some(isElementLevel)) continue;
    const focusOnly = parts.every((part) => /:focus(?:-visible)?$/.test(part));
    for (const { property, important } of declarations(body)) {
      if (property.startsWith("--") || important) continue;
      if (focusOnly && FOCUS_PROPERTIES.has(property)) continue;
      out.push(`${selector.replace(/\s+/g, " ")} { ${property} }`);
    }
  }
  return out;
}

describe("element base rules (D-349)", () => {
  it("sets nothing a utility can set from an unlayered element-level rule", () => {
    expect(unlayeredElementRules(CSS)).toEqual([]);
    for (const [selector, property] of [
      ["a", "color"],
      ["button", "cursor"],
      ["button:active", "opacity"],
    ]) {
      const rule = rules(CSS).find(
        ({ selector: list, body }) =>
          selectorParts(list).includes(selector) && declarations(body).some((d) => d.property === property),
      );
      expect(rule?.layers, `${selector} { ${property} }`).toEqual(["@layer base"]);
    }
  });

  it("the scan flags unlayered element rules and passes layered, class, token, important and focus ones", () => {
    const css = [
      "a { color: inherit; text-decoration: none; }",
      "button:active, .card:active { opacity: .85; }",
      ":where(button, nav a) { position: relative; }",
      "input[type=\"range\"] { height: 6px; }",
      "@media (hover: hover) { :where(button) svg { transform: scale(1.02); } }",
      "@keyframes fade { from { opacity: 0; } to { opacity: 1; } }",
      "@layer base { button { cursor: pointer; } }",
      ".card a { color: red; }",
      ":root { --canvas: #fff; }",
      "html body * { box-shadow: none !important; }",
      ":focus-visible { outline: 2px solid; outline-offset: 2px; }",
      "input[type=\"range\"]:focus-visible { box-shadow: 0 0 0 2px; }",
      ":focus-visible { color: red; }",
    ].join("\n");
    expect(unlayeredElementRules(css)).toEqual([
      "a { color }",
      "a { text-decoration }",
      "button:active, .card:active { opacity }",
      ":where(button, nav a) { position }",
      "input[type=\"range\"] { height }",
      ":where(button) svg { transform }",
      ":focus-visible { color }",
    ]);
  });
});
