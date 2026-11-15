import { readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";

// D-282: aria-label on an element with no role (a generic div or span) is
// prohibited, so axe reports aria-prohibited-attr and screen readers may
// ignore the name. A loading placeholder takes role="status"; a named section
// takes role="group".

const SRC = resolve(__dirname, "../..");
const ROOTS = ["components/sessions", "components/features/sessions"];
const GENERIC = new Set(["div", "span", "p"]);

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return entry.name.endsWith(".tsx") && !entry.name.includes(".test.") ? [path] : [];
  });
}

/** Every generic element with aria-label and no role, as `file:line <tag>`. */
function namedGenerics(path: string, text = readFileSync(path, "utf8")): string[] {
  const source = ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const found: string[] = [];
  const visit = (node: ts.Node) => {
    if ((ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) && GENERIC.has(node.tagName.getText(source))) {
      const names = node.attributes.properties.flatMap((attribute) =>
        ts.isJsxAttribute(attribute) ? [attribute.name.getText(source)] : [],
      );
      if (names.includes("aria-label") && !names.includes("role")) {
        const { line } = source.getLineAndCharacterOfPosition(node.getStart(source));
        found.push(`${relative(SRC, path)}:${line + 1} <${node.tagName.getText(source)}>`);
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return found;
}

describe("aria-label only on elements with a role (D-282)", () => {
  it("no generic element in the sessions screens carries aria-label without a role", () => {
    const offenders = ROOTS.flatMap((root) => sourceFiles(join(SRC, root))).flatMap((path) => namedGenerics(path));
    expect(offenders).toEqual([]);
  });

  it("the scan flags a named div and spares one with a role", () => {
    const probe = join(SRC, "components/sessions/probe.tsx");
    const fixture = [
      'export const A = () => <div aria-label="Loading" />;',
      'export const B = () => <div role="status" aria-label="Loading" />;',
      'export const C = () => <button aria-label="Send" />;',
    ].join("\n");
    expect(namedGenerics(probe, fixture)).toEqual(["components/sessions/probe.tsx:1 <div>"]);
  });
});
