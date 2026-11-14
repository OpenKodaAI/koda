import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import * as ts from "typescript";
import { describe, expect, it } from "vitest";
import { INSECURE_TRANSPORT_ERROR_CODE } from "@/lib/web-operator-session-constants";

/**
 * The auth screens fold every credential failure into one generic message
 * (apps/web/CLAUDE.md, "Auth screens"). Two answers are the exceptions, because
 * neither depends on an account: the plain-HTTP refusal, which the routes decide
 * from the transport before reading any credential, and the per-client rate
 * limit (a 429, ADR-038), which `rateLimitedAuthMessage` reads from the status.
 * This pins both halves: the guide names the exceptions, and neither a screen
 * nor any module it imports reads a field that an ApiError takes from the
 * response (`reason`, `status`, `code`, `retryable`, `retryAfterSeconds`)
 * except for those two answers and the "service unavailable" check for a 5xx
 * or no response.
 */

const WEB_ROOT = resolve(__dirname, "../..");
// The sources behind /setup, /login, /forgot-password and /settings/account.
const AUTH_SCREEN_DIRS = [
  "src/components/auth",
  "src/components/setup",
  "src/components/account",
  "src/app/login",
  "src/app/setup",
  "src/app/forgot-password",
  "src/app/settings/account",
];

/** The fields an ApiError takes from the response: the body's `error.code`, the status and what errors.ts derives from it, and `Retry-After`. */
const RESPONSE_FIELDS = ["reason", "status", "code", "retryable", "retryAfterSeconds"] as const;
type ResponseField = (typeof RESPONSE_FIELDS)[number];

/**
 * Modules the screens reach whose reads of these names are reviewed here
 * instead of scanned, each for the fields named: they build, carry or route
 * errors without choosing what a screen says, or the name is their own. Every
 * other module a screen imports, directly or not, is scanned like the screen
 * itself, so an error-copy helper cannot move a branch out of sight. Add an
 * entry only for a module that never picks a message from an error.
 */
const REVIEWED: Record<string, { fields: ResponseField[]; why: string }> = {
  "src/lib/errors.ts": {
    fields: ["reason", "status", "code", "retryable", "retryAfterSeconds"],
    why: "defines ApiError and derives `code` and `retryable` from the status",
  },
  "src/lib/http-client.ts": {
    fields: ["status", "code"],
    why: "turns a response into an ApiError; a 401 on a session request sends the browser to /login",
  },
  "src/lib/control-plane.ts": {
    fields: ["status"],
    why: "the server-side control-plane client the auth pages call",
  },
  "src/lib/auth-guard.ts": {
    fields: ["status"],
    why: "the server-side session guard: a 401 there means no session, before any screen renders",
  },
  "src/lib/tour.ts": { fields: ["status"], why: "the product tour's own persisted step `status`" },
  "src/components/ui/action-button.tsx": {
    fields: ["status"],
    why: "the button's own `status` prop (idle, pending, success, error)",
  },
  "src/components/ui/async-feedback.tsx": { fields: ["status"], why: "the feedback component's own `status` prop" },
};

type SourceHost = { read(path: string): string; isFile(path: string): boolean };

const DISK: SourceHost = {
  read: (path) => readFileSync(path, "utf8"),
  isFile: (path) => {
    try {
      return statSync(path).isFile();
    } catch {
      return false;
    }
  },
};

function authRule(): string {
  const guide = readFileSync(join(WEB_ROOT, "CLAUDE.md"), "utf8");
  const section = guide.split(/^## /m).find((part) => part.startsWith("Auth screens"));
  if (!section) throw new Error('apps/web/CLAUDE.md has no "## Auth screens" section');
  return section;
}

function authScreenFiles(): string[] {
  return AUTH_SCREEN_DIRS.flatMap((dir) =>
    readdirSync(join(WEB_ROOT, dir), { recursive: true, encoding: "utf8" })
      .filter((name) => /\.tsx?$/.test(name) && !name.includes(".test.") && !name.endsWith(".d.ts"))
      .map((name) => join(WEB_ROOT, dir, name)),
  );
}

/**
 * The file an import names, for `@/…` and relative specifiers; `null` for a
 * package or a non-code asset. An in-repo specifier that resolves to nothing
 * fails the test, so a module the resolver misses cannot escape the scan.
 */
function resolveImport(host: SourceHost, fromFile: string, specifier: string): string | null {
  let base: string;
  if (specifier.startsWith("@/")) base = join(WEB_ROOT, "src", specifier.slice(2));
  else if (specifier.startsWith(".")) base = resolve(dirname(fromFile), specifier);
  else return null;
  const stem = base.replace(/\.(m?js|jsx)$/, "");
  const candidates = [base, `${stem}.ts`, `${stem}.tsx`, join(base, "index.ts"), join(base, "index.tsx")];
  const code = candidates.find((candidate) => /\.tsx?$/.test(candidate) && host.isFile(candidate));
  if (code) return code;
  if (host.isFile(base)) return null;
  throw new Error(`${relative(WEB_ROOT, fromFile)} imports ${specifier}, which resolves to no file`);
}

/** The screens and every module they import, directly or not, as paths relative to apps/web. */
function importClosure(host: SourceHost, roots: string[]): string[] {
  const seen = new Set<string>();
  const queue = [...roots];
  while (queue.length > 0) {
    const file = queue.shift() as string;
    if (seen.has(file)) continue;
    seen.add(file);
    // Static imports, `export … from`, `import type`, `import()` and `require()`.
    for (const { fileName } of ts.preProcessFile(host.read(file), true, true).importedFiles) {
      const target = resolveImport(host, file, fileName);
      if (target && !seen.has(target)) queue.push(target);
    }
  }
  return [...seen].map((file) => relative(WEB_ROOT, file)).sort();
}

function parse(fileName: string, source: string): ts.SourceFile {
  return ts.createSourceFile(
    fileName,
    source,
    ts.ScriptTarget.Latest,
    true,
    fileName.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
}

/** The screens and every module they import, parsed once. */
function closureSources(): Array<[string, ts.SourceFile]> {
  return importClosure(DISK, authScreenFiles()).map((file): [string, ts.SourceFile] => [
    file,
    parse(file, DISK.read(join(WEB_ROOT, file))),
  ]);
}

function isReviewed(file: string, field: ResponseField): boolean {
  return Object.hasOwn(REVIEWED, file) && REVIEWED[file].fields.includes(field);
}

type FieldRead = { line: number; text: string; allowed: boolean };

function enclosingFunctionName(node: ts.Node): string | null {
  for (let current = node.parent; current; current = current.parent) {
    if (ts.isFunctionDeclaration(current)) return current.name?.text ?? null;
    if (ts.isArrowFunction(current) || ts.isFunctionExpression(current) || ts.isMethodDeclaration(current)) {
      const holder = current.parent;
      if (ts.isMethodDeclaration(current) && ts.isIdentifier(current.name)) return current.name.text;
      if (holder && ts.isVariableDeclaration(holder) && ts.isIdentifier(holder.name)) return holder.name.text;
      return null;
    }
  }
  return null;
}

/** `<identifier>.<field>`, with no optional chaining, cast or brackets around it. */
function isPlainAccess(access: ts.PropertyAccessExpression): boolean {
  return !access.questionDotToken && ts.isIdentifier(access.expression);
}

/** The one allowed `reason` read: `<identifier>.reason === INSECURE_TRANSPORT_ERROR_CODE`, anywhere. */
function isTransportRefusalCheck(access: ts.PropertyAccessExpression): boolean {
  if (!isPlainAccess(access)) return false;
  const comparison = access.parent;
  return (
    ts.isBinaryExpression(comparison) &&
    comparison.left === access &&
    comparison.operatorToken.kind === ts.SyntaxKind.EqualsEqualsEqualsToken &&
    ts.isIdentifier(comparison.right) &&
    comparison.right.text === "INSECURE_TRANSPORT_ERROR_CODE"
  );
}

/** The status comparisons a screen may branch on, by the function that holds them. */
const ALLOWED_STATUS_CHECKS: Record<string, Array<[ts.SyntaxKind, number]>> = {
  // The per-client rate limit (ADR-038), the same for every identifier.
  rateLimitedAuthMessage: [[ts.SyntaxKind.ExclamationEqualsEqualsToken, 429]],
  // "Service unavailable": a 5xx, or no response at all.
  isUpstreamFailure: [
    [ts.SyntaxKind.GreaterThanEqualsToken, 500],
    [ts.SyntaxKind.EqualsEqualsEqualsToken, 0],
  ],
};

/** An allowed status check: `<identifier>.status <op> <number>`, inside the function that owns it. */
function isAllowedStatusCheck(access: ts.PropertyAccessExpression): boolean {
  if (!isPlainAccess(access)) return false;
  const comparison = access.parent;
  if (!ts.isBinaryExpression(comparison) || comparison.left !== access) return false;
  if (!ts.isNumericLiteral(comparison.right)) return false;
  const owner = enclosingFunctionName(access);
  const allowed = owner && Object.hasOwn(ALLOWED_STATUS_CHECKS, owner) ? ALLOWED_STATUS_CHECKS[owner] : [];
  return allowed.some(
    ([operator, value]) => comparison.operatorToken.kind === operator && Number(comparison.right.getText()) === value,
  );
}

/** Which plain property reads of each field are allowed. Any other spelling never is. */
const ALLOWED_ACCESS: Record<ResponseField, (access: ts.PropertyAccessExpression) => boolean> = {
  reason: isTransportRefusalCheck,
  status: isAllowedStatusCheck,
  // The wait in the 429 message (ADR-038), read only after the status check.
  retryAfterSeconds: (access) => isPlainAccess(access) && enclosingFunctionName(access) === "rateLimitedAuthMessage",
  // Derived from the status alone (401 UNAUTHORIZED, 403 FORBIDDEN, 404 NOT_FOUND, 5xx retryable).
  code: () => false,
  retryable: () => false,
};

/** `x.<field> = …`: a write, as in a translation table or a constructor, not a branch. */
function isAssignmentTarget(access: ts.PropertyAccessExpression): boolean {
  const parent = access.parent;
  return (
    ts.isBinaryExpression(parent) && parent.left === access && parent.operatorToken.kind === ts.SyntaxKind.EqualsToken
  );
}

/** Whether an object literal is the left side of a destructuring assignment, `({ status } = error)`. */
function isAssignmentPattern(literal: ts.ObjectLiteralExpression): boolean {
  let node: ts.Node = literal;
  for (;;) {
    const parent: ts.Node = node.parent;
    if (ts.isParenthesizedExpression(parent) || ts.isArrayLiteralExpression(parent)) node = parent;
    else if (ts.isPropertyAssignment(parent) && parent.initializer === node) node = parent.parent;
    else if (ts.isBinaryExpression(parent)) {
      return parent.left === node && parent.operatorToken.kind === ts.SyntaxKind.EqualsToken;
    } else if (ts.isForOfStatement(parent) || ts.isForInStatement(parent)) return parent.initializer === node;
    else return false;
  }
}

/**
 * Every read of `field`: `x.f`, `x?.f`, `(x as T).f`, `x["f"]`, `` x[`f`] ``,
 * `{ f }` and `{ f: g }` in a declaration or a destructuring assignment, and
 * `"f" in x`. A screen that branched on any of them for a failed auth call (a
 * 423 for a locked account, `code === "FORBIDDEN"`, an `error.code` such as
 * `UNKNOWN_USER`) would show a per-failure message. A variable or parameter
 * that happens to share the name, an object literal key, a write, a comment, an
 * i18n key such as `auth.insecure_transport.reason` and the string in
 * `role="status"` are not reads.
 */
function fieldReads(sourceFile: ts.SourceFile, field: ResponseField): FieldRead[] {
  const lines = sourceFile.text.split("\n");
  const reads: FieldRead[] = [];
  const isFieldName = (node: ts.Node | undefined) =>
    !!node && (ts.isIdentifier(node) || ts.isStringLiteralLike(node)) && node.text === field;
  const record = (node: ts.Node, allowed: boolean) => {
    const line = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
    reads.push({ line, text: lines[line - 1].trim(), allowed });
  };
  const visit = (node: ts.Node) => {
    if (ts.isPropertyAccessExpression(node) && node.name.text === field) {
      if (!isAssignmentTarget(node)) record(node.name, ALLOWED_ACCESS[field](node));
    } else if (ts.isElementAccessExpression(node) && isFieldName(node.argumentExpression)) {
      record(node.argumentExpression, false);
    } else if (
      ts.isBindingElement(node) &&
      ts.isObjectBindingPattern(node.parent) &&
      isFieldName(node.propertyName ?? node.name)
    ) {
      record(node, false);
    } else if (
      (ts.isShorthandPropertyAssignment(node) || ts.isPropertyAssignment(node)) &&
      isFieldName(node.name) &&
      ts.isObjectLiteralExpression(node.parent) &&
      isAssignmentPattern(node.parent)
    ) {
      record(node, false);
    } else if (
      ts.isBinaryExpression(node) &&
      node.operatorToken.kind === ts.SyntaxKind.InKeyword &&
      isFieldName(node.left)
    ) {
      record(node.left, false);
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return reads;
}

function scan(field: ResponseField, ...body: string[]): FieldRead[] {
  return fieldReads(parse("fixture.tsx", body.join("\n") + "\n"), field);
}

describe("auth screens error contract", () => {
  it("apps/web/CLAUDE.md names the transport refusal and the rate limit as the only specific auth errors", () => {
    const rule = authRule();
    expect(rule).toContain("Never introduce a branch that renders a specific error message");
    expect(rule).toMatch(/only allowed exceptions are two/i);
    expect(rule).toContain(`\`${INSECURE_TRANSPORT_ERROR_CODE}\``);
    expect(rule).toMatch(/before any credential is read/i);
    expect(rule).toContain("`rateLimitedAuthMessage`");
    expect(rule).toContain("`429`");
    // The guide names what the contract test checks.
    for (const field of RESPONSE_FIELDS) expect(rule).toContain(`\`${field}\``);
    expect(rule).toMatch(/every module they import/i);
  });

  it.each([
    [
      "reason",
      [
        "src/components/auth/forgot-password-screen.tsx",
        "src/components/auth/login-screen.tsx",
        "src/components/setup/step-create-account.tsx",
      ],
    ],
    [
      "status",
      [
        "src/components/auth/forgot-password-screen.tsx",
        "src/components/auth/login-screen.tsx",
        "src/components/setup/step-create-account.tsx",
        "src/lib/auth-rate-limit-message.ts",
      ],
    ],
    ["retryAfterSeconds", ["src/lib/auth-rate-limit-message.ts"]],
    ["code", []],
    ["retryable", []],
  ] satisfies Array<[ResponseField, string[]]>)(
    "the screens and their imports read `%s` only where the contract allows",
    (field, filesThatRead) => {
      const reads = closureSources()
        .filter(([file]) => !isReviewed(file, field))
        .flatMap(([file, sourceFile]) => fieldReads(sourceFile, field).map((read) => ({ file, ...read })));

      expect([...new Set(reads.map(({ file }) => file))].sort()).toEqual(filesThatRead);
      expect(reads.filter(({ allowed }) => !allowed)).toEqual([]);
    },
  );

  it("scans the shared helpers the screens import, and reviews only what the list names", () => {
    const sources = new Map(closureSources());

    expect([...sources.keys()]).toEqual(
      expect.arrayContaining([
        "src/lib/auth-rate-limit-message.ts",
        "src/lib/retry-after.ts",
        "src/lib/cookie-transport.ts",
        "src/hooks/use-app-i18n.ts",
      ]),
    );
    // Each reviewed entry is still reached and still reads every field it names:
    // a stale one would hide a module that later starts choosing copy.
    const stale = Object.entries(REVIEWED).flatMap(([file, { fields }]) =>
      fields
        .filter((field) => {
          const sourceFile = sources.get(file);
          return !sourceFile || fieldReads(sourceFile, field).length === 0;
        })
        .map((field) => `${file}: ${field}`),
    );
    expect(stale).toEqual([]);
  });

  describe("the import closure", () => {
    const screen = join(WEB_ROOT, "src/components/auth/fixture-screen.tsx");
    function closureOf(files: Record<string, string>): string[] {
      const absolute = new Map(Object.entries(files).map(([file, source]) => [join(WEB_ROOT, file), source]));
      const host: SourceHost = {
        read: (path) => absolute.get(path) ?? "",
        isFile: (path) => absolute.has(path),
      };
      return importClosure(host, [screen]);
    }

    it("follows @/ and relative imports, re-exports, type imports and dynamic imports, transitively", () => {
      expect(
        closureOf({
          "src/components/auth/fixture-screen.tsx": [
            'import { copyFor } from "@/lib/auth-error-copy";',
            'import type { Shape } from "./shape";',
            'export * from "../setup/barrel";',
            'const lazy = () => import("@/lib/lazy-copy");',
            'import { Button } from "@/components/ui/button";',
            'import "./screen.css";',
            'import { useState } from "react";',
          ].join("\n"),
          "src/lib/auth-error-copy.ts": 'export { lockedCopy } from "./auth-error-copy/locked.js";',
          "src/lib/auth-error-copy/locked.ts": "export const lockedCopy = 1;",
          "src/components/auth/shape.ts": "export type Shape = {};",
          "src/components/setup/barrel/index.ts": 'export * from "@/lib/deep-copy";',
          "src/lib/deep-copy.ts": "export const deep = 1;",
          "src/lib/lazy-copy.ts": "export const lazy = 1;",
          "src/components/ui/button.tsx": "export function Button() {}",
          "src/components/auth/screen.css": "",
        }),
      ).toEqual([
        "src/components/auth/fixture-screen.tsx",
        "src/components/auth/shape.ts",
        "src/components/setup/barrel/index.ts",
        "src/components/ui/button.tsx",
        "src/lib/auth-error-copy.ts",
        "src/lib/auth-error-copy/locked.ts",
        "src/lib/deep-copy.ts",
        "src/lib/lazy-copy.ts",
      ]);
    });

    it("fails on an in-repo import it cannot resolve", () => {
      expect(() =>
        closureOf({ "src/components/auth/fixture-screen.tsx": 'import { x } from "@/lib/missing-helper";' }),
      ).toThrow(/imports @\/lib\/missing-helper, which resolves to no file/);
    });

    it("finds a status branch moved into a helper the screen imports", () => {
      // The review's case: the lockout copy lives in a new src/lib helper, not in the screen.
      const files: Record<string, string> = {
        "src/components/auth/fixture-screen.tsx": 'import { authErrorCopy } from "@/lib/auth-error-copy";',
        "src/lib/auth-error-copy.ts": [
          "export function authErrorCopy(error: ApiError) {",
          '  if (error.status === 423) return "This account is locked.";',
          "  return null;",
          "}",
        ].join("\n"),
      };
      const reads = closureOf(files).flatMap((file) =>
        fieldReads(parse(file, files[file]), "status").map((read) => ({ file, ...read })),
      );

      expect(reads).toEqual([
        {
          file: "src/lib/auth-error-copy.ts",
          line: 2,
          text: 'if (error.status === 423) return "This account is locked.";',
          allowed: false,
        },
      ]);
    });
  });

  describe("the field scan", () => {
    it("allows the 429 in rateLimitedAuthMessage and the 5xx check in isUpstreamFailure", () => {
      expect(
        scan(
          "status",
          "export function rateLimitedAuthMessage(error: unknown) {",
          "  if (!(error instanceof ApiError) || error.status !== 429) return null;",
          "}",
          "function isUpstreamFailure(error: unknown): boolean {",
          "  if (error instanceof ApiError) return error.status >= 500 || error.status === 0;",
          "  return true;",
          "}",
          "const isUpstreamFailureToo = (error: ApiError) => error.status >= 500;",
          'const status = await getStatus(); const banner = <p role="status">{status.authenticated}</p>;',
        ).map(({ allowed }) => allowed),
      ).toEqual([true, true, true, false]);
    });

    it("allows the Retry-After wait only in rateLimitedAuthMessage", () => {
      expect(
        scan(
          "retryAfterSeconds",
          "export function rateLimitedAuthMessage(error: ApiError) {",
          "  const seconds = error.retryAfterSeconds;",
          "}",
          "function onError(error: ApiError) {",
          '  if (error.retryAfterSeconds > 600) setError("This account is locked for a while.");',
          "}",
        ).map(({ line, allowed }) => [line, allowed]),
      ).toEqual([
        [2, true],
        [5, false],
      ]);
    });

    it("allows the transport check and skips comments, i18n keys, object keys, names and writes", () => {
      expect(
        scan(
          "reason",
          "function onError(error: unknown) {",
          "  // error.reason carries the route's error.code",
          '  const hint = t("auth.insecure_transport.reason");',
          '  const table = { insecure_transport: { reason: "Plain HTTP" } };',
          '  resources.auth.reason = { ok: "Ok" };',
          "  const reason = 1; const code = reason;",
          "  return error instanceof ApiError && error.reason === INSECURE_TRANSPORT_ERROR_CODE;",
          "}",
        ),
      ).toEqual([
        {
          line: 7,
          text: "return error instanceof ApiError && error.reason === INSECURE_TRANSPORT_ERROR_CODE;",
          allowed: true,
        },
      ]);
    });

    const spellings = (field: ResponseField, value: string): Array<[ResponseField, string, string]> =>
      [
        ["a plain read", `if (error.${field} === ${value}) setError("This account is locked.");`],
        ["optional chaining", `if ((error as ApiError)?.${field} === ${value}) setError("No such account.");`],
        ["a cast", `if ((error as ApiError).${field} === ${value}) setError("This account is locked.");`],
        ["brackets", `if (error["${field}"] === ${value}) setError("This account is locked.");`],
        ["template brackets", `if (error[\`${field}\`] === ${value}) setError("This account is locked.");`],
        ["destructuring", `const { ${field} } = error as ApiError;`],
        ["renamed destructuring", `const { ${field}: why } = error as ApiError;`],
        ["a destructuring assignment", `({ ${field} } = error as ApiError);`],
        ["a renamed destructuring assignment", `({ ${field}: why } = error as ApiError);`],
        ["the in operator", `if ("${field}" in (error as object)) setError("Something specific.");`],
        ["a switch", `switch ((error as ApiError).${field}) { case ${value}: setError("Locked."); }`],
      ].map(([how, line]): [ResponseField, string, string] => [field, how, line]);

    it.each([
      ...spellings("reason", '"LOCKED"'),
      ["reason", "optional chaining on the transport check", "return error?.reason === INSECURE_TRANSPORT_ERROR_CODE;"],
      ...spellings("status", "423"),
      [
        "status",
        "a 429 check outside rateLimitedAuthMessage",
        'if (error instanceof ApiError && error.status === 429) setError("Slow down.");',
      ],
      ...spellings("code", '"FORBIDDEN"'),
      // The review's case: errors.ts maps a 403 to code FORBIDDEN, so this is a status branch.
      [
        "code",
        "a check in a catch block",
        'if (error instanceof ApiError && error.code === "FORBIDDEN") setError("This account is locked.");',
      ],
      ...spellings("retryable", "false"),
      ...spellings("retryAfterSeconds", "900"),
    ] satisfies Array<[ResponseField, string, string]>)("flags a read of %s through %s", (field, _spelling, line) => {
      const reads = scan(field, "function onError(error: unknown) {", `  ${line}`, "}");

      expect(reads).toHaveLength(1);
      expect(reads[0]).toMatchObject({ line: 2, allowed: false });
    });

    it("skips a write to the field", () => {
      expect(scan("status", 'resources.auth.status = { ok: "Ok" };', "this.code = code;")).toEqual([]);
      expect(scan("code", "this.code = options.code ?? 0;").map(({ text }) => text)).toEqual([
        "this.code = options.code ?? 0;",
      ]);
    });

    it.each([
      ["rateLimitedAuthMessage", "error.status === 423"],
      ["isUpstreamFailure", "error.status === 423"],
      ["isUpstreamFailure", "error.status >= 400"],
      ["isUpstreamFailure", "error?.status >= 500"],
    ])("flags a check in %s other than its own: %s", (owner, check) => {
      const reads = scan("status", `function ${owner}(error: ApiError) {`, `  return ${check};`, "}");

      expect(reads).toHaveLength(1);
      expect(reads[0]).toMatchObject({ line: 2, allowed: false });
    });
  });
});
