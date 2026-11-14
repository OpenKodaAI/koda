import { readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { INSECURE_TRANSPORT_ERROR_CODE } from "@/lib/web-operator-session-constants";

/**
 * The auth screens fold every credential failure into one generic message
 * (apps/web/CLAUDE.md, "Auth screens"). The plain-HTTP refusal is the one
 * exception, because the routes decide it from the transport before reading
 * any credential. This pins both halves: the guide names the exception, and no
 * screen branches on any other error code.
 */

const WEB_ROOT = resolve(__dirname, "../..");
const AUTH_SCREEN_DIRS = ["src/components/auth", "src/components/setup"];

function authScreensRule(): string {
  const guide = readFileSync(join(WEB_ROOT, "CLAUDE.md"), "utf8");
  const section = guide.split(/^## /m).find((part) => part.startsWith("Auth screens"));
  if (!section) throw new Error('apps/web/CLAUDE.md has no "## Auth screens" section');
  return section;
}

function authScreenSources(): Array<[string, string]> {
  return AUTH_SCREEN_DIRS.flatMap((dir) =>
    readdirSync(join(WEB_ROOT, dir))
      .filter((name) => name.endsWith(".tsx") && !name.includes(".test."))
      .map((name): [string, string] => [
        `${dir}/${name}`,
        readFileSync(join(WEB_ROOT, dir, name), "utf8"),
      ]),
  );
}

describe("auth screens error contract", () => {
  it("apps/web/CLAUDE.md names the transport refusal as the only specific auth error", () => {
    const rule = authScreensRule();
    expect(rule).toContain("Never introduce a branch that renders a specific error message");
    expect(rule).toContain(`\`${INSECURE_TRANSPORT_ERROR_CODE}\``);
    expect(rule).toMatch(/only allowed exception/i);
    expect(rule).toMatch(/before any credential is read/i);
  });

  it("branches on no error code but the transport refusal", () => {
    // `error.reason` carries the route's `error.code`; reading it any other way
    // in an auth screen would reopen a per-failure message.
    const reads = authScreenSources().flatMap(([file, source]) =>
      Array.from(source.matchAll(/\b[A-Za-z_$][\w$]*\.reason\b(?!["'\w])[^\n]*/g), (match) => ({
        file,
        read: match[0],
      })),
    );

    expect(reads.map(({ file }) => file).sort()).toEqual([
      "src/components/auth/forgot-password-screen.tsx",
      "src/components/auth/login-screen.tsx",
      "src/components/setup/step-create-account.tsx",
    ]);
    for (const { file, read } of reads) {
      expect(read, file).toMatch(/^\w+\.reason === INSECURE_TRANSPORT_ERROR_CODE;$/);
    }
  });
});
