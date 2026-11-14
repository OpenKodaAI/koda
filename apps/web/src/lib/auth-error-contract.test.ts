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
 * on any error code but the transport refusal.
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

function authScreensRule(): string {
  const guide = readFileSync(join(WEB_ROOT, "CLAUDE.md"), "utf8");
  const section = guide.split(/^## /m).find((part) => part.startsWith("Auth screens"));
  if (!section) throw new Error('apps/web/CLAUDE.md has no "## Auth screens" section');
  return section;
}

function authScreenSources(): Array<[string, string]> {
  return AUTH_SCREEN_DIRS.flatMap((dir) =>
    readdirSync(join(WEB_ROOT, dir), { recursive: true, encoding: "utf8" })
      .filter((name) => /\.tsx?$/.test(name) && !name.includes(".test.") && !name.endsWith(".d.ts"))
      .map((name): [string, string] => [`${dir}/${name}`, readFileSync(join(WEB_ROOT, dir, name), "utf8")]),
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
  const sourceFile = ts.createSourceFile(
    fileName,
    source,
    ts.ScriptTarget.Latest,
    true,
    fileName.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
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
