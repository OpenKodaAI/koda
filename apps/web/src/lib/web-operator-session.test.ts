import { NextResponse } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearPendingRecoveryCookie,
  clearWebOperatorSessionCookie,
  sealWebOperatorToken,
  setOwnerExistsHintCookie,
  setPendingRecoveryCookie,
  setWebOperatorSessionCookie,
  unsealWebOperatorToken,
} from "@/lib/web-operator-session";
import {
  OWNER_EXISTS_HINT_COOKIE,
  PENDING_RECOVERY_COOKIE,
  WEB_OPERATOR_SESSION_COOKIE,
} from "@/lib/web-operator-session-constants";

describe("web operator session secret", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("round-trips a token with a configured secret in production", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("WEB_OPERATOR_SESSION_SECRET", "0123456789abcdef0123456789abcdef");

    const sealed = sealWebOperatorToken("session-token");

    expect(sealed).not.toContain("session-token");
    expect(unsealWebOperatorToken(sealed)).toBe("session-token");
  });

  it("rejects the .env.example placeholder in production", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("WEB_OPERATOR_SESSION_SECRET", "replace-with-a-random-web-session-secret");

    expect(() => sealWebOperatorToken("session-token")).toThrow(/placeholder is rejected/);
  });

  it("does not unseal a token sealed under a different secret", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("WEB_OPERATOR_SESSION_SECRET", "0123456789abcdef0123456789abcdef");
    const sealed = sealWebOperatorToken("session-token");

    vi.stubEnv("WEB_OPERATOR_SESSION_SECRET", "fedcba9876543210fedcba9876543210");

    expect(unsealWebOperatorToken(sealed)).toBeNull();
  });
});

describe("web operator cookie flags", () => {
  // Every helper that writes an operator cookie, with the cookie it writes.
  const helpers: ReadonlyArray<[string, string, (response: NextResponse) => void]> = [
    ["setWebOperatorSessionCookie", WEB_OPERATOR_SESSION_COOKIE, (r) => setWebOperatorSessionCookie(r, "session-token")],
    ["clearWebOperatorSessionCookie", WEB_OPERATOR_SESSION_COOKIE, (r) => clearWebOperatorSessionCookie(r)],
    ["setOwnerExistsHintCookie(true)", OWNER_EXISTS_HINT_COOKIE, (r) => setOwnerExistsHintCookie(r, true)],
    ["setOwnerExistsHintCookie(false)", OWNER_EXISTS_HINT_COOKIE, (r) => setOwnerExistsHintCookie(r, false)],
    ["setPendingRecoveryCookie(true)", PENDING_RECOVERY_COOKIE, (r) => setPendingRecoveryCookie(r, true)],
    ["clearPendingRecoveryCookie", PENDING_RECOVERY_COOKIE, (r) => clearPendingRecoveryCookie(r)],
  ];

  function cookieWrittenBy(write: (response: NextResponse) => void, name: string) {
    const response = NextResponse.json({});
    write(response);
    const cookie = response.cookies.get(name);
    expect(cookie).toBeDefined();
    return cookie;
  }

  beforeEach(() => {
    vi.stubEnv("WEB_OPERATOR_SESSION_SECRET", "0123456789abcdef0123456789abcdef");
    // A developer or CI shell may export either switch; each test sets what it needs.
    vi.stubEnv("SECURE_COOKIES", "");
    vi.stubEnv("ALLOW_INSECURE_COOKIES", "");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it.each(helpers)("%s marks %s Secure in production", (_helper, name, write) => {
    vi.stubEnv("NODE_ENV", "production");
    expect(cookieWrittenBy(write, name)?.secure).toBe(true);
  });

  it.each(helpers)("%s leaves %s plain in development without SECURE_COOKIES", (_helper, name, write) => {
    vi.stubEnv("NODE_ENV", "development");
    expect(cookieWrittenBy(write, name)?.secure).toBe(false);
  });

  it.each(helpers)("%s marks %s Secure in development with SECURE_COOKIES=true", (_helper, name, write) => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("SECURE_COOKIES", "true");
    expect(cookieWrittenBy(write, name)?.secure).toBe(true);
  });
});
