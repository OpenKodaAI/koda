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
});
