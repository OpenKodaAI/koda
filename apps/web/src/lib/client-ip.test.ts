import { describe, expect, it } from "vitest";
import { clientIpFromHeaders, forwardedClientIpHeaders } from "./client-ip";

describe("clientIpFromHeaders", () => {
  it("uses the rightmost x-forwarded-for entry and ignores client-supplied ones", () => {
    const headers = new Headers({ "x-forwarded-for": "10.9.9.9, 1.2.3.4, 198.51.100.7" });
    expect(clientIpFromHeaders(headers)).toBe("198.51.100.7");
  });

  it("accepts the socket address Next.js fills in", () => {
    expect(clientIpFromHeaders(new Headers({ "x-forwarded-for": "::FFFF:127.0.0.1" }))).toBe(
      "::ffff:127.0.0.1",
    );
    expect(clientIpFromHeaders(new Headers({ "x-forwarded-for": "2001:db8::1" }))).toBe("2001:db8::1");
  });

  it("returns null for missing or malformed values", () => {
    expect(clientIpFromHeaders(new Headers())).toBeNull();
    expect(clientIpFromHeaders(undefined)).toBeNull();
    expect(clientIpFromHeaders({} as never)).toBeNull();
    expect(clientIpFromHeaders(new Headers({ "x-forwarded-for": "1.2.3.4, evil host" }))).toBeNull();
    expect(clientIpFromHeaders(new Headers({ "x-forwarded-for": "1.2.3.4," }))).toBeNull();
  });
});

describe("forwardedClientIpHeaders", () => {
  it("builds the upstream header only when a client address is known", () => {
    expect(forwardedClientIpHeaders(new Headers({ "x-forwarded-for": "198.51.100.7" }))).toEqual({
      "X-Forwarded-For": "198.51.100.7",
    });
    expect(forwardedClientIpHeaders(new Headers())).toEqual({});
  });
});
