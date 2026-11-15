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
// became color: 0.8125rem, an invalid colour, and the size never applied. Only
// a colour token may go without a type hint; anything else takes length: (or
// color: to say it is a colour).

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

function isColour(name: RegExp, values: Map<string, string[]>, seen = new Set<string>()): boolean {
  const matching = [...values.entries()].filter(([candidate]) => name.test(candidate));
  if (matching.length === 0) return false;
  return matching.every(([candidate, list]) =>
    list.every((value) => {
      const alias = /^var\(\s*(--[\w-]+)\s*\)$/.exec(value);
      if (!alias) return COLOUR_VALUE.test(value);
      if (seen.has(candidate)) return false;
      return isColour(matcher(alias[1]), values, new Set([...seen, candidate]));
    }),
  );
}

/**
 * Every text-[var(--x)] or text-(--x) without a type hint whose --x is not a
 * colour token, as `file:line class -> fix`.
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
    [...text.matchAll(untyped)]
      .filter((match) => !isColour(matcher(match[1] ?? match[2]), values))
      .map((match) => {
        const line = text.slice(0, match.index).split("\n").length;
        const fix = match[1]
          ? match[0].replace("text-[var(", "text-[length:var(")
          : match[0].replace("text-(", "text-(length:");
        return `${relative(SRC, path)}:${line} ${match[0]} compiles to color:, write ${fix} (or color: for a colour)`;
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
  it("a text-[var(--x)] without a type hint names a colour token (D-330)", () => {
    const files = sourceFiles(SRC).map((path) => ({ path, text: readFileSync(path, "utf8") }));
    expect(untypedTextReferences(files)).toEqual([]);
  });

  it("the D-330 scan flags untyped sizes and unknown types, and passes colours and hinted classes", () => {
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
      "components/probe.tsx:1 text-[var(--font-size-sm)] compiles to color:, write text-[length:var(--font-size-sm)] (or color: for a colour)",
      "components/probe.tsx:4 text-(--font-size-sm) compiles to color:, write text-(length:--font-size-sm) (or color: for a colour)",
      "components/probe.tsx:4 text-[var(--gap)] compiles to color:, write text-[length:var(--gap)] (or color: for a colour)",
      "components/probe.tsx:6 text-[var(--pad)] compiles to color:, write text-[length:var(--pad)] (or color: for a colour)",
    ]);
  });
});
