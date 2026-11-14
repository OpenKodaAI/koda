import { afterEach, describe, expect, it, vi } from "vitest";
import { sealWebOperatorToken, unsealWebOperatorToken } from "@/lib/web-operator-session";

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
