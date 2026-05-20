import fs from "node:fs";
import path from "node:path";
import * as ts from "typescript";
import { describe, expect, it } from "vitest";
import { SUPPORTED_LANGUAGES, translateForLanguage } from "@/lib/i18n";
import { resources } from "@/lib/i18n-resources";

type FlatResources = Map<string, string>;

const UI_SOURCE_ROOT = path.join(process.cwd(), "src");
const VISIBLE_STRING_ATTRIBUTES = new Set([
  "aria-label",
  "placeholder",
  "title",
  "alt",
  "label",
  "description",
  "emptyLabel",
  "loadingLabel",
  "clearLabel",
  "closeLabel",
  "subtitle",
  "eyebrow",
  "heading",
  "message",
]);

const SMOKE_KEYS = [
  "common.search",
  "routeMeta.runtime.title",
  "auth.login.submit",
  "account.profile.photo.choose",
  "settings.sections.models.label",
  "runtime.attach.terminalTimeout",
  "sessions.searchPlaceholder",
  "memory.filters.title",
  "costs.filters.period",
  "executions.searchPlaceholder",
  "dlq.filters.eligible",
  "schedules.jobs",
  "routines.editor.actions.save",
  "tour.actions.start",
];

function flattenResources(value: unknown, prefix = "", out: FlatResources = new Map()) {
  if (!value || typeof value !== "object") return out;

  for (const [key, entry] of Object.entries(value)) {
    const nextKey = prefix ? `${prefix}.${key}` : key;
    if (typeof entry === "string") {
      out.set(nextKey, entry);
      continue;
    }
    flattenResources(entry, nextKey, out);
  }

  return out;
}

function interpolationTokens(value: string) {
  return Array.from(value.matchAll(/\{\{\s*([\w.-]+)\s*\}\}/g))
    .map((match) => match[1])
    .sort();
}

function listSourceFiles(dir: string, out: string[] = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === ".next" || entry.name === "__fixtures__" || entry.name === "node_modules") {
      continue;
    }
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      listSourceFiles(fullPath, out);
      continue;
    }
    if (/\.(ts|tsx)$/.test(entry.name) && !entry.name.includes(".test.")) {
      out.push(fullPath);
    }
  }
  return out;
}

function isScannedUiSource(filePath: string) {
  const relativePath = path.relative(UI_SOURCE_ROOT, filePath).replaceAll(path.sep, "/");
  if (relativePath.startsWith("app/api/")) return false;
  return ![
    "lib/i18n-resources.ts",
    "lib/i18n-generated-literals.ts",
    "lib/i18n-generated-ui.ts",
    "lib/i18n-static-copy.ts",
  ].includes(relativePath);
}

function isIgnoredLiteral(value: string) {
  const trimmed = value.replace(/\s+/g, " ").trim();
  if (!trimmed) return true;
  if (!/[A-Za-zÀ-ÿ]/.test(trimmed)) return true;
  if (trimmed === "Koda") return true;
  return /^https?:|^\/|^~\/|^[A-Z0-9_]+$|^[*.]+$|^[\d.]+$/.test(trimmed);
}

function literalText(node: ts.Node) {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
    return node.text;
  }
  return null;
}

function propertyNameText(name: ts.PropertyName) {
  if (ts.isIdentifier(name) || ts.isStringLiteral(name) || ts.isNumericLiteral(name)) {
    return name.text;
  }
  return null;
}

describe("i18n contract", () => {
  it("keeps every resource key present and token-compatible in every supported language", () => {
    const flattened = Object.fromEntries(
      SUPPORTED_LANGUAGES.map((language) => [
        language,
        flattenResources(resources[language].translation),
      ]),
    );
    const base = flattened["en-US"];

    for (const language of SUPPORTED_LANGUAGES) {
      const languageResources = flattened[language];
      const missingKeys = Array.from(base.keys()).filter((key) => !languageResources.has(key));
      const extraKeys = Array.from(languageResources.keys()).filter((key) => !base.has(key));
      expect(missingKeys, `${language} missing translation keys`).toEqual([]);
      expect(extraKeys, `${language} extra translation keys`).toEqual([]);

      for (const [key, baseValue] of base) {
        const translated = languageResources.get(key);
        expect(translated, `${language}.${key}`).toBeTruthy();
        expect(interpolationTokens(translated ?? ""), `${language}.${key} interpolation`).toEqual(
          interpolationTokens(baseValue),
        );
      }
    }
  });

  it("resolves critical frontend namespaces for every supported language", () => {
    for (const language of SUPPORTED_LANGUAGES) {
      for (const key of SMOKE_KEYS) {
        const translated = translateForLanguage(language, key);
        expect(translated, `${language}.${key}`).toBeTruthy();
        expect(translated, `${language}.${key}`).not.toBe(key);
      }
    }
  });

  it("does not ship fixed frontend copy as source literals", () => {
    const violations: string[] = [];

    for (const filePath of listSourceFiles(UI_SOURCE_ROOT).filter(isScannedUiSource)) {
      const source = fs.readFileSync(filePath, "utf8");
      const sourceFile = ts.createSourceFile(
        filePath,
        source,
        ts.ScriptTarget.Latest,
        true,
        filePath.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
      );

      function report(node: ts.Node, message: string) {
        const { line, character } = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
        violations.push(`${path.relative(process.cwd(), filePath)}:${line + 1}:${character + 1} ${message}`);
      }

      function visit(node: ts.Node) {
        if (ts.isJsxText(node)) {
          const text = node.getText(sourceFile).replace(/[{}]/g, " ").replace(/\s+/g, " ").trim();
          if (!isIgnoredLiteral(text)) {
            report(node, `hardcoded JSX text "${text}"`);
          }
        }

        if (ts.isJsxAttribute(node) && node.initializer && ts.isStringLiteral(node.initializer)) {
          const name = node.name.getText(sourceFile);
          if (VISIBLE_STRING_ATTRIBUTES.has(name) && !isIgnoredLiteral(node.initializer.text)) {
            report(node, `hardcoded ${name}="${node.initializer.text}"`);
          }
        }

        if (ts.isCallExpression(node)) {
          const callee = node.expression.getText(sourceFile);
          const firstArg = node.arguments[0];
          const secondArg = node.arguments[1];
          if ((callee === "tl" || callee === "translateLiteral") && firstArg && literalText(firstArg)) {
            report(node, `${callee} must not receive a fixed source literal`);
          }
          if (callee === "translateLiteralForLanguage" && secondArg && literalText(secondArg)) {
            report(node, "translateLiteralForLanguage must not receive a fixed source literal");
          }
        }

        if (
          ts.isPropertyAssignment(node) &&
          propertyNameText(node.name) === "defaultValue" &&
          literalText(node.initializer)
        ) {
          report(node, "translation defaultValue must live in i18n resources");
        }

        ts.forEachChild(node, visit);
      }

      visit(sourceFile);
    }

    expect(violations).toEqual([]);
  });
});
