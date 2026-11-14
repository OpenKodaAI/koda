import { readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import * as ts from "typescript";
import { describe, expect, it } from "vitest";
import { INSECURE_TRANSPORT_ERROR_CODE } from "@/lib/web-operator-session-constants";

/**
 * The auth screens fold every credential failure into one generic message
 * (apps/web/CLAUDE.md, "Auth screens"). Two answers are the exceptions, because
 * neither depends on an account: the plain-HTTP refusal, which the routes decide
 * from the transport before reading any credential, and the per-client rate
 * limit (a 429, ADR-038), which `rateLimitedAuthMessage` reads from the status.
 * This pins both halves: the guide names the exceptions, and no screen branches
 * on any error code but the transport refusal, or on any HTTP status but the
 * 429 and the "service unavailable" check for a 5xx or no response.
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
// The error helpers those screens share, scanned with them.
const AUTH_ERROR_HELPERS = ["src/lib/auth-rate-limit-message.ts"];

function authScreensRule(): string {
  const guide = readFileSync(join(WEB_ROOT, "CLAUDE.md"), "utf8");
  const section = guide.split(/^## /m).find((part) => part.startsWith("Auth screens"));
  if (!section) throw new Error('apps/web/CLAUDE.md has no "## Auth screens" section');
  return section;
}

function authScreenSources(): Array<[string, string]> {
  const screens = AUTH_SCREEN_DIRS.flatMap((dir) =>
    readdirSync(join(WEB_ROOT, dir), { recursive: true, encoding: "utf8" })
      .filter((name) => /\.tsx?$/.test(name) && !name.includes(".test.") && !name.endsWith(".d.ts"))
      .map((name): [string, string] => [`${dir}/${name}`, readFileSync(join(WEB_ROOT, dir, name), "utf8")]),
  );
  const helpers = AUTH_ERROR_HELPERS.map((file): [string, string] => [
    file,
    readFileSync(join(WEB_ROOT, file), "utf8"),
  ]);
  return [...screens, ...helpers];
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

type ReasonRead = { line: number; text: string; allowed: boolean };

/**
 * The one allowed read: `<identifier>.reason === INSECURE_TRANSPORT_ERROR_CODE`,
 * with no optional chaining, cast or brackets around it.
 */
function isTransportRefusalCheck(name: ts.Identifier): boolean {
  const access = name.parent;
  if (!ts.isPropertyAccessExpression(access) || access.name !== name) return false;
  if (access.questionDotToken || !ts.isIdentifier(access.expression)) return false;
  const comparison = access.parent;
  return (
    ts.isBinaryExpression(comparison) &&
    comparison.left === access &&
    comparison.operatorToken.kind === ts.SyntaxKind.EqualsEqualsEqualsToken &&
    ts.isIdentifier(comparison.right) &&
    comparison.right.text === "INSECURE_TRANSPORT_ERROR_CODE"
  );
}

/**
 * Every place a source names `reason`, the property that carries the route's
 * `error.code`: as an identifier (`x.reason`, `x?.reason`, `(x as T).reason`,
 * `{ reason }`, `{ reason: r }`) or as a string (`x["reason"]`,
 * `` x[`reason`] ``, `"reason" in x`). Comments and i18n keys such as
 * `auth.insecure_transport.reason` are not reads.
 */
function reasonReads(fileName: string, source: string): ReasonRead[] {
  const sourceFile = parse(fileName, source);
  const lines = source.split("\n");
  const reads: ReasonRead[] = [];
  const visit = (node: ts.Node) => {
    const named = ts.isIdentifier(node) || ts.isStringLiteralLike(node);
    if (named && node.text === "reason") {
      const line = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
      reads.push({
        line,
        text: lines[line - 1].trim(),
        allowed: ts.isIdentifier(node) && isTransportRefusalCheck(node),
      });
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return reads;
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

/**
 * An allowed status check: `<identifier>.status <op> <number>`, with no
 * optional chaining, cast or brackets, inside the function that owns it.
 */
function isAllowedStatusCheck(access: ts.PropertyAccessExpression): boolean {
  if (access.questionDotToken || !ts.isIdentifier(access.expression)) return false;
  const comparison = access.parent;
  if (!ts.isBinaryExpression(comparison) || comparison.left !== access) return false;
  if (!ts.isNumericLiteral(comparison.right)) return false;
  const owner = enclosingFunctionName(access);
  const allowed = owner && Object.hasOwn(ALLOWED_STATUS_CHECKS, owner) ? ALLOWED_STATUS_CHECKS[owner] : [];
  return allowed.some(
    ([operator, value]) => comparison.operatorToken.kind === operator && Number(comparison.right.getText()) === value,
  );
}

/**
 * Every read of a `status` property: `x.status`, `x?.status`,
 * `(x as T).status`, `x["status"]`, `` x[`status`] ``, `{ status }`,
 * `{ status: s }` and `"status" in x`. A screen that branched on the HTTP
 * status of a failed auth call (a 423 for a locked account, a 404 for an
 * unknown one) would show a per-failure message as surely as one reading
 * `reason`. A variable that happens to be named `status`, or the string in
 * `role="status"`, is not a read.
 */
function statusReads(fileName: string, source: string): ReasonRead[] {
  const sourceFile = parse(fileName, source);
  const lines = source.split("\n");
  const reads: ReasonRead[] = [];
  const isStatusName = (node: ts.Node | undefined) =>
    !!node && (ts.isIdentifier(node) || ts.isStringLiteralLike(node)) && node.text === "status";
  const record = (node: ts.Node, allowed: boolean) => {
    const line = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
    reads.push({ line, text: lines[line - 1].trim(), allowed });
  };
  const visit = (node: ts.Node) => {
    if (ts.isPropertyAccessExpression(node) && node.name.text === "status") {
      record(node.name, isAllowedStatusCheck(node));
    } else if (ts.isElementAccessExpression(node) && isStatusName(node.argumentExpression)) {
      record(node.argumentExpression, false);
    } else if (
      ts.isBindingElement(node) &&
      ts.isObjectBindingPattern(node.parent) &&
      isStatusName(node.propertyName ?? node.name)
    ) {
      record(node, false);
    } else if (
      ts.isBinaryExpression(node) &&
      node.operatorToken.kind === ts.SyntaxKind.InKeyword &&
      isStatusName(node.left)
    ) {
      record(node.left, false);
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return reads;
}

describe("auth screens error contract", () => {
  it("apps/web/CLAUDE.md names the transport refusal and the rate limit as the only specific auth errors", () => {
    const rule = authScreensRule();
    expect(rule).toContain("Never introduce a branch that renders a specific error message");
    expect(rule).toMatch(/only allowed exceptions are two/i);
    expect(rule).toContain(`\`${INSECURE_TRANSPORT_ERROR_CODE}\``);
    expect(rule).toMatch(/before any credential is read/i);
    expect(rule).toContain("`rateLimitedAuthMessage`");
    expect(rule).toContain("`429`");
  });

  it("branches on no error code but the transport refusal", () => {
    // `error.reason` carries the route's `error.code`; reading it any other way
    // in an auth screen would reopen a per-failure message.
    const reads = authScreenSources().flatMap(([file, source]) =>
      reasonReads(file, source).map((read) => ({ file, ...read })),
    );

    expect([...new Set(reads.map(({ file }) => file))].sort()).toEqual([
      "src/components/auth/forgot-password-screen.tsx",
      "src/components/auth/login-screen.tsx",
      "src/components/setup/step-create-account.tsx",
    ]);
    expect(reads.filter(({ allowed }) => !allowed)).toEqual([]);
  });

  it("branches on no HTTP status but the rate limit and an unavailable service", () => {
    const reads = authScreenSources().flatMap(([file, source]) =>
      statusReads(file, source).map((read) => ({ file, ...read })),
    );

    expect([...new Set(reads.map(({ file }) => file))].sort()).toEqual([
      "src/components/auth/forgot-password-screen.tsx",
      "src/components/auth/login-screen.tsx",
      "src/components/setup/step-create-account.tsx",
      "src/lib/auth-rate-limit-message.ts",
    ]);
    expect(reads.filter(({ allowed }) => !allowed)).toEqual([]);
  });

  describe("the status scan", () => {
    function scan(...body: string[]): ReasonRead[] {
      return statusReads("fixture.tsx", body.join("\n") + "\n");
    }

    it("allows the 429 in rateLimitedAuthMessage and the 5xx check in isUpstreamFailure", () => {
      expect(
        scan(
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

    it.each([
      ["a status check in a catch block", 'if (error instanceof ApiError && error.status === 423) setError("This account is locked.");'],
      ["a 429 check outside rateLimitedAuthMessage", 'if (error instanceof ApiError && error.status === 429) setError("Slow down.");'],
      ["optional chaining", 'if ((error as ApiError)?.status === 404) setError("No such account.");'],
      ["a cast", 'if ((error as ApiError).status === 423) setError("This account is locked.");'],
      ["brackets", 'if (error["status"] === 423) setError("This account is locked.");'],
      ["template brackets", 'if (error[`status`] === 423) setError("This account is locked.");'],
      ["destructuring", "const { status } = error as ApiError;"],
      ["renamed destructuring", "const { status: code } = error as ApiError;"],
      ["the in operator", 'if ("status" in (error as object)) setError("Something specific.");'],
      ["a switch", 'switch ((error as ApiError).status) { case 423: setError("Locked."); }'],
    ])("flags %s", (_spelling, line) => {
      const reads = scan("function onError(error: unknown) {", `  ${line}`, "}");

      expect(reads).toHaveLength(1);
      expect(reads[0]).toMatchObject({ line: 2, allowed: false });
    });

    it.each([
      ["rateLimitedAuthMessage", "error.status === 423"],
      ["isUpstreamFailure", "error.status === 423"],
      ["isUpstreamFailure", "error.status >= 400"],
      ["isUpstreamFailure", "error?.status >= 500"],
    ])("flags a check in %s other than its own: %s", (owner, check) => {
      const reads = scan(`function ${owner}(error: ApiError) {`, `  return ${check};`, "}");

      expect(reads).toHaveLength(1);
      expect(reads[0]).toMatchObject({ line: 2, allowed: false });
    });
  });

  describe("the reason scan", () => {
    function scan(...body: string[]): ReasonRead[] {
      return reasonReads(
        "fixture.tsx",
        ["function onError(error: unknown) {", ...body.map((line) => `  ${line}`), "}", ""].join("\n"),
      );
    }

    it("allows the transport check and skips comments and i18n keys", () => {
      expect(
        scan(
          "// error.reason carries the route's error.code",
          'const hint = t("auth.insecure_transport.reason");',
          "return error instanceof ApiError && error.reason === INSECURE_TRANSPORT_ERROR_CODE;",
        ),
      ).toEqual([
        {
          line: 4,
          text: "return error instanceof ApiError && error.reason === INSECURE_TRANSPORT_ERROR_CODE;",
          allowed: true,
        },
      ]);
    });

    it.each([
      ["a plain read", 'if (error.reason === "LOCKED") setError("This account is locked.");'],
      ["a cast with optional chaining", 'if ((error as ApiError)?.reason === "INVALID_CREDENTIALS") setError("Wrong password for this account.");'],
      ["optional chaining", 'if (error instanceof ApiError && error?.reason === "UNKNOWN_USER") setError("No such account.");'],
      ["a cast", 'if ((error as ApiError).reason === "LOCKED") setError("This account is locked.");'],
      ["brackets", 'if (error["reason"] === "LOCKED") setError("This account is locked.");'],
      ["template brackets", 'if (error[`reason`] === "LOCKED") setError("This account is locked.");'],
      ["destructuring", 'const { reason } = error as ApiError;'],
      ["renamed destructuring", 'const { reason: why } = error as ApiError;'],
      ["the in operator", 'if ("reason" in (error as object)) setError("Something specific.");'],
      ["a switch", 'switch ((error as ApiError).reason) { case "LOCKED": setError("Locked."); }'],
      ["optional chaining on the transport check", "return error?.reason === INSECURE_TRANSPORT_ERROR_CODE;"],
    ])("flags a read of reason through %s", (_spelling, line) => {
      const reads = scan(line);

      expect(reads).toHaveLength(1);
      expect(reads[0]).toMatchObject({ line: 2, allowed: false });
    });
  });
});
