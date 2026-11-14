import { describe, expect, it } from "vitest";
import { clientIpFromHeaders, forwardedClientIpHeaders, isLoopbackAddress, rateLimitKey } from "./client-ip";

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

describe("rateLimitKey", () => {
  it("groups an IPv6 client's /64 so rotating its source address does not reset the window", () => {
    expect(rateLimitKey("2001:db8:1:2:aaaa::1")).toBe("2001:db8:1:2::/64");
    expect(rateLimitKey("2001:DB8:1:2:bbbb:cccc:dddd:eeee")).toBe("2001:db8:1:2::/64");
    expect(rateLimitKey("2001:db8:0001:0002::ffff")).toBe("2001:db8:1:2::/64");
    expect(rateLimitKey("2001:db8::1")).toBe("2001:db8:0:0::/64");
    expect(rateLimitKey("::1")).toBe("0:0:0:0::/64");
    expect(rateLimitKey("64:ff9b::192.0.2.1")).toBe("64:ff9b:0:0::/64");
    expect(rateLimitKey("2001:db8:1:3::1")).not.toBe(rateLimitKey("2001:db8:1:2::1"));
  });

  it("keys IPv4 clients by their full address", () => {
    expect(rateLimitKey("198.51.100.7")).toBe("198.51.100.7");
    expect(rateLimitKey("::ffff:198.51.100.7")).toBe("198.51.100.7");
  });

  it("falls back to the raw value for addresses it cannot parse", () => {
    expect(rateLimitKey("1:2:3")).toBe("1:2:3");
    expect(rateLimitKey("1::2::3")).toBe("1::2::3");
  });
});

describe("isLoopbackAddress", () => {
  it("recognizes the loopback addresses the control plane trusts", () => {
    expect(isLoopbackAddress("127.0.0.1")).toBe(true);
    expect(isLoopbackAddress("::1")).toBe(true);
    expect(isLoopbackAddress("::ffff:127.0.0.1")).toBe(true);
    expect(isLoopbackAddress("198.51.100.7")).toBe(false);
    expect(isLoopbackAddress(null)).toBe(false);
  });
});
