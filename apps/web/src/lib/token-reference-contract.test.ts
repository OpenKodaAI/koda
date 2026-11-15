import { readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

// M8-E5-T3 (TD-133): every custom property the app reads with var() is set
// somewhere in the app. An undefined var() makes its whole declaration invalid
// at computed-value time, so the background turns transparent or the colour
// falls back to inherit, and nothing reports it. A var() with a fallback still
// needs a definition: a hook that nothing ever sets is dead indirection, so
// write the fallback value instead.

const SRC = resolve(__dirname, "..");

// Set at runtime by a library, not by app code: Radix (popper and select
// geometry) and Tailwind's own utility internals.
const SET_BY_LIBRARY = /^--(?:radix|tw)-/;

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return /\.(css|tsx?)$/.test(entry.name) && !entry.name.includes(".test.") ? [path] : [];
  });
}

function withoutComments(text: string): string {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, (comment) => comment.replace(/[^\n]/g, ""))
    .replace(/(^|[^:"'`\w])\/\/.*$/gm, "$1");
}

/** Every custom property name the text sets. */
function definitions(text: string): Set<string> {
  const names = new Set<string>();
  // CSS declarations, Tailwind arbitrary properties ([--x:value]) and inline
  // style strings ("--x: value").
  for (const [, name] of text.matchAll(/(?<![\w-])(--[\w-]+)\s*:/g)) names.add(name);
  // Names handled as string literals: style object keys ({ "--x": value }),
  // setProperty("--x", value), next/font's variable: "--x".
  for (const [, name] of text.matchAll(/["'`](--[\w-]+)["'`]/g)) names.add(name);
  return names;
}

/**
 * Every var() reference in the text, and every Tailwind v4 shorthand that
 * compiles to one (bg-(--x), border-(color:--x), text-(length:--x)); a ${...}
 * in a template literal is a wildcard.
 */
function references(text: string): { name: string; line: number }[] {
  const patterns = [
    /var\(\s*(--[\w-]*(?:\$\{[^}]*\}[\w-]*)*)/g,
    /(?<=[a-z\d]-)\((?:[a-z-]+:)?(--[\w-]*(?:\$\{[^}]*\}[\w-]*)*)\)/g,
  ];
  return patterns
    .flatMap((pattern) => [...text.matchAll(pattern)])
    .sort((a, b) => (a.index ?? 0) - (b.index ?? 0))
    .map((match) => ({
      name: match[1],
      line: text.slice(0, match.index).split("\n").length,
    }));
}

function matcher(reference: string): RegExp {
  const pattern = reference
    .split(/\$\{[^}]*\}/)
    .map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("[\\w-]+");
  return new RegExp(`^${pattern}$`);
}

/** Every reference to a custom property nothing defines, as `file:line --name`. */
function undefinedReferences(files: { path: string; text: string }[]): string[] {
  const sources = files.map(({ path, text }) => ({ path, text: withoutComments(text) }));
  const defined = new Set(sources.flatMap(({ text }) => [...definitions(text)]));
  return sources.flatMap(({ path, text }) =>
    references(text)
      .filter(({ name }) => !SET_BY_LIBRARY.test(name))
      .filter(({ name }) => {
        if (!name.includes("${")) return !defined.has(name);
        const pattern = matcher(name);
        return ![...defined].some((candidate) => pattern.test(candidate));
      })
      .map(({ name, line }) => `${relative(SRC, path)}:${line} ${name}`),
  );
}

// D-330: Tailwind v4 cannot tell what type a var() holds, so text-[var(--x)]
// and text-(--x) compile to color: whatever --x is. text-[var(--font-size-sm)]
// became color: 0.8125rem, an invalid colour, and the size never applied. So
// every arbitrary text-[var()] or text-(--x) says its type: length: for a
// size, color: for a colour. The values below only pick which fix to name.

const COLOUR_VALUE =
  /^(?:#[\da-f]{3,8}|(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color|color-mix|light-dark)\(|transparent$|currentcolor$|white$|black$)/i;

/** Every value the text gives a custom property, by name. */
function definedValues(text: string): Map<string, string[]> {
  const values = new Map<string, string[]>();
  const add = (name: string, value: string) =>
    values.set(name, [...(values.get(name) ?? []), value.trim()]);
  // CSS declarations and inline style strings ("--x: value").
  for (const [, name, value] of text.matchAll(/(?<![\w-])(--[\w-]+)\s*:\s*([^;{}"'`\]]+)/g)) {
    add(name, value);
  }
  // Style object keys: { "--x": "value" } or { "--x": `value` }.
  for (const [, name, value] of text.matchAll(/["'](--[\w-]+)["']\s*:\s*["'`]([^"'`]*)/g)) {
    add(name, value);
  }
  return values;
}

/** Whether every value of the tokens the name matches, through var() aliases, matches kind. */
function holds(name: RegExp, kind: RegExp, values: Map<string, string[]>, seen = new Set<string>()): boolean {
  const matching = [...values.entries()].filter(([candidate]) => name.test(candidate));
  if (matching.length === 0) return false;
  return matching.every(([candidate, list]) =>
    list.every((value) => {
      const alias = /^var\(\s*(--[\w-]+)\s*\)$/.exec(value);
      if (!alias) return kind.test(value);
      if (seen.has(candidate)) return false;
      return holds(matcher(alias[1]), kind, values, new Set([...seen, candidate]));
    }),
  );
}

/**
 * Every text-[var(--x)] or text-(--x) without a type hint, as `file:line class
 * fix`: color: when --x is a colour token, length: otherwise.
 */
function untypedTextReferences(files: { path: string; text: string }[]): string[] {
  const sources = files.map(({ path, text }) => ({ path, text: withoutComments(text) }));
  const values = new Map<string, string[]>();
  for (const { text } of sources) {
    for (const [name, list] of definedValues(text)) values.set(name, [...(values.get(name) ?? []), ...list]);
  }
  const untyped =
    /(?<![\w-])text-(?:\[var\(\s*(--[\w-]*(?:\$\{[^}]*\}[\w-]*)*)[^\]]*\]|\((--[\w-]*(?:\$\{[^}]*\}[\w-]*)*)\))/g;
  return sources.flatMap(({ path, text }) =>
    [...text.matchAll(untyped)].map((match) => {
      const line = text.slice(0, match.index).split("\n").length;
      const colour = holds(matcher(match[1] ?? match[2]), COLOUR_VALUE, values);
      const hint = colour ? "color:" : "length:";
      const fix = match[1] ? match[0].replace("text-[var(", `text-[${hint}var(`) : match[0].replace("text-(", `text-(${hint}`);
      return colour
        ? `${relative(SRC, path)}:${line} ${match[0]} has no type hint, write ${fix}`
        : `${relative(SRC, path)}:${line} ${match[0]} compiles to color:, write ${fix} (or color: for a colour)`;
    }),
  );
}

// D-349: --transition-fast is a transition shorthand (120ms cubic-bezier(...)),
// not a time, so duration-[var(--transition-fast)] compiles to an invalid
// transition-duration and the transition drops to 0s. Every arbitrary
// duration-, delay- or ease- var() names a token that holds a time or an easing.

const TIME_VALUE = /^-?(?:\d+\.?\d*|\.\d+)m?s$/;
const EASING_VALUE = /^(?:linear|ease|ease-in|ease-out|ease-in-out|step-start|step-end)$|^(?:cubic-bezier|steps|linear)\(/;

/** Every duration-, delay- or ease- var() whose token is not a time or an easing, as `file:line class`. */
function mistypedMotionReferences(files: { path: string; text: string }[]): string[] {
  const sources = files.map(({ path, text }) => ({ path, text: withoutComments(text) }));
  const values = new Map<string, string[]>();
  for (const { text } of sources) {
    for (const [name, list] of definedValues(text)) values.set(name, [...(values.get(name) ?? []), ...list]);
  }
  const motion = /(?<![\w-])(duration|delay|ease)-(?:\[var\(\s*(--[\w-]+)\s*\)\]|\((--[\w-]+)\))/g;
  return sources.flatMap(({ path, text }) =>
    [...text.matchAll(motion)]
      .filter((match) => !holds(matcher(match[2] ?? match[3]), match[1] === "ease" ? EASING_VALUE : TIME_VALUE, values))
      .map((match) => {
        const line = text.slice(0, match.index).split("\n").length;
        return `${relative(SRC, path)}:${line} ${match[0]} is not ${match[1] === "ease" ? "an easing" : "a time"}`;
      }),
  );
}

describe("design token references (M8-E5-T3)", () => {
  it("no component, style or helper reads a custom property that nothing defines", () => {
    const files = sourceFiles(SRC).map((path) => ({ path, text: readFileSync(path, "utf8") }));
    expect(files.some(({ path }) => path.endsWith("globals.css"))).toBe(true);
    expect(undefinedReferences(files)).toEqual([]);
  });

  it("the scan flags undefined names, dead fallback hooks, unmatched template names and the (--x) shorthand", () => {
    const css = [
      ":root { --panel: #fff; --tone-info-bg: #eef; }",
      ".a { background: var(--panel); color: var(--panel-muted); }",
      ".b { background: var(--sticky-bg, var(--panel)); }",
      "/* var(--in-a-comment) */",
    ].join("\n");
    const tsx = [
      'export const A = () => <div className="bg-[var(--surface-canvas)] [--local:1px] p-[var(--local)]" />;',
      "export const tone = (name: string) => `var(--tone-${name}-bg)`;",
      "export const tint = (name: string) => `var(--tone-${name}-tint)`;",
      'export const style = { "--set-inline": "1px", width: "var(--set-inline)" };',
      'export const radix = "w-[var(--radix-popover-trigger-width)]";',
      'export const B = () => <div className="bg-(--surface-base) border-(color:--panel) text-(length:--font-size-tiny)" />;',
    ].join("\n");
    expect(
      undefinedReferences([
        { path: join(SRC, "app/probe.css"), text: css },
        { path: join(SRC, "components/probe.tsx"), text: tsx },
      ]),
    ).toEqual([
      "app/probe.css:2 --panel-muted",
      "app/probe.css:3 --sticky-bg",
      "components/probe.tsx:1 --surface-canvas",
      "components/probe.tsx:3 --tone-${name}-tint",
      "components/probe.tsx:6 --surface-base",
      "components/probe.tsx:6 --font-size-tiny",
    ]);
  });

  it("every arbitrary text-[var(--x)] or text-(--x) carries a length: or color: hint (D-330)", () => {
    const files = sourceFiles(SRC).map((path) => ({ path, text: readFileSync(path, "utf8") }));
    expect(untypedTextReferences(files)).toEqual([]);
  });

  it("the D-330 scan flags every unhinted class, names color: for a colour token, and passes hinted classes", () => {
    const css = [
      ":root { --text-primary: #101010; --font-size-sm: 0.8125rem; --tone-info-text: rgb(1 2 3); }",
      ":root { --tone-danger-text: #f00; --alias: var(--text-primary); --gap: var(--font-size-sm); }",
    ].join("\n");
    const tsx = [
      'export const A = () => <p className="text-[var(--text-primary)] text-[var(--font-size-sm)]" />;',
      'export const B = () => <p className="text-[length:var(--font-size-sm)] text-[color:var(--gap)]" />;',
      "export const tone = (name: string) => `text-[var(--tone-${name}-text)]`;",
      'export const C = () => <p className="text-(--font-size-sm) text-(--alias) text-[var(--gap)]" />;',
      'export const style = { "--mention": `color-mix(in srgb, red 50%, white)`, "--pad": "4px" };',
      'export const D = () => <p className="text-[var(--mention)] text-[var(--pad)]" />;',
    ].join("\n");
    expect(
      untypedTextReferences([
        { path: join(SRC, "app/probe.css"), text: css },
        { path: join(SRC, "components/probe.tsx"), text: tsx },
      ]),
    ).toEqual([
      "components/probe.tsx:1 text-[var(--text-primary)] has no type hint, write text-[color:var(--text-primary)]",
      "components/probe.tsx:1 text-[var(--font-size-sm)] compiles to color:, write text-[length:var(--font-size-sm)] (or color: for a colour)",
      "components/probe.tsx:3 text-[var(--tone-${name}-text)] has no type hint, write text-[color:var(--tone-${name}-text)]",
      "components/probe.tsx:4 text-(--font-size-sm) compiles to color:, write text-(length:--font-size-sm) (or color: for a colour)",
      "components/probe.tsx:4 text-(--alias) has no type hint, write text-(color:--alias)",
      "components/probe.tsx:4 text-[var(--gap)] compiles to color:, write text-[length:var(--gap)] (or color: for a colour)",
      "components/probe.tsx:6 text-[var(--mention)] has no type hint, write text-[color:var(--mention)]",
      "components/probe.tsx:6 text-[var(--pad)] compiles to color:, write text-[length:var(--pad)] (or color: for a colour)",
    ]);
  });

  it("every arbitrary duration-, delay- or ease- var() names a time or an easing token (D-349)", () => {
    const files = sourceFiles(SRC).map((path) => ({ path, text: readFileSync(path, "utf8") }));
    expect(mistypedMotionReferences(files)).toEqual([]);
  });

  it("the D-349 motion scan flags a transition shorthand and passes time and easing tokens", () => {
    const css = [
      ":root { --transition-fast: 120ms cubic-bezier(0.22, 1, 0.36, 1); --ease-out-quart: cubic-bezier(0.22, 1, 0.36, 1); }",
      ":root { --duration-fast: 120ms; --delay: .2s; --ease-alias: var(--ease-out-quart); }",
    ].join("\n");
    const tsx = [
      'export const A = () => <b className="transition-colors duration-[var(--transition-fast)] ease-[var(--transition-fast)]" />;',
      'export const B = () => <b className="duration-[var(--duration-fast)] delay-(--delay) ease-[var(--ease-alias)]" />;',
      'export const C = () => <b className="duration-(--ease-out-quart) duration-[120ms] ease-[var(--ease-out-quart)]" />;',
    ].join("\n");
    expect(
      mistypedMotionReferences([
        { path: join(SRC, "app/probe.css"), text: css },
        { path: join(SRC, "components/probe.tsx"), text: tsx },
      ]),
    ).toEqual([
      "components/probe.tsx:1 duration-[var(--transition-fast)] is not a time",
      "components/probe.tsx:1 ease-[var(--transition-fast)] is not an easing",
      "components/probe.tsx:3 duration-(--ease-out-quart) is not a time",
    ]);
  });
});
