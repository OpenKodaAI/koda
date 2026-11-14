import { afterEach, describe, expect, it, vi } from "vitest";
import {
  insecureCookieTransport,
  isLoopbackHostname,
  secureCookiesEnabled,
} from "@/lib/cookie-transport";

afterEach(() => {
  vi.unstubAllEnvs();
});

function production() {
  vi.stubEnv("NODE_ENV", "production");
}

/** Headers as Next.js hands them to the proxy and route handlers over a plain socket. */
function plainHttp(host: string, extra: Record<string, string> = {}): Headers {
  return new Headers({ host, "x-forwarded-proto": "http", "x-forwarded-host": host, ...extra });
}

describe("secureCookiesEnabled", () => {
  it("marks cookies Secure in production", () => {
    production();
    expect(secureCookiesEnabled()).toBe(true);
  });

  it("keeps Secure in production even when ALLOW_INSECURE_COOKIES is set", () => {
    // The opt-out is development-only; a production opt-out is M1-E1-T11.
    production();
    vi.stubEnv("ALLOW_INSECURE_COOKIES", "true");
    expect(secureCookiesEnabled()).toBe(true);
  });

  it("leaves cookies plain in development unless SECURE_COOKIES=true", () => {
    vi.stubEnv("NODE_ENV", "development");
    expect(secureCookiesEnabled()).toBe(false);
    vi.stubEnv("SECURE_COOKIES", "true");
    expect(secureCookiesEnabled()).toBe(true);
    vi.stubEnv("ALLOW_INSECURE_COOKIES", "true");
    expect(secureCookiesEnabled()).toBe(false);
  });
});

describe("isLoopbackHostname", () => {
  it.each(["localhost", "LOCALHOST", "koda.localhost", "127.0.0.1", "127.8.9.10", "[::1]"])(
    "treats %s as loopback",
    (hostname) => {
      expect(isLoopbackHostname(hostname)).toBe(true);
    },
  );

  it.each(["192.168.1.10", "10.0.0.5", "100.101.102.103", "koda.example.com", "0.0.0.0", "[fe80::1]", "localhost.example.com", "128.0.0.1"])(
    "treats %s as a remote host",
    (hostname) => {
      expect(isLoopbackHostname(hostname)).toBe(false);
    },
  );
});

describe("insecureCookieTransport", () => {
  it("reports plain HTTP from a LAN address in production (J-14)", () => {
    production();
    expect(insecureCookieTransport(plainHttp("192.168.1.10:3000"))).toEqual({
      origin: "http://192.168.1.10:3000",
    });
  });

  it("reports plain HTTP behind a proxy that says the scheme was http", () => {
    production();
    const headers = new Headers({
      host: "127.0.0.1:3000",
      "x-forwarded-proto": "http",
      "x-forwarded-host": "koda.lan",
    });
    expect(insecureCookieTransport(headers)).toEqual({ origin: "http://koda.lan" });
  });

  it("reads the first hop of a multi-value forwarded header", () => {
    production();
    const headers = new Headers({
      host: "koda.lan",
      "x-forwarded-proto": "http, https",
      "x-forwarded-host": "koda.lan, 127.0.0.1:3000",
    });
    expect(insecureCookieTransport(headers)).toEqual({ origin: "http://koda.lan" });
  });

  it.each(["localhost:3000", "127.0.0.1:3000", "[::1]:3000", "koda.localhost:3000"])(
    "accepts plain HTTP on the loopback host %s, which browsers treat as secure",
    (host) => {
      production();
      expect(insecureCookieTransport(plainHttp(host))).toBeNull();
    },
  );

  it("accepts HTTPS terminated by a proxy", () => {
    production();
    const headers = new Headers({
      host: "koda.example.com",
      "x-forwarded-proto": "https",
      "x-forwarded-host": "koda.example.com",
    });
    expect(insecureCookieTransport(headers)).toBeNull();
  });

  it("accepts a browser that sends Fetch Metadata, which it only does to a secure URL", () => {
    // A TLS proxy that sends no X-Forwarded-Proto looks like plain HTTP to the
    // dashboard; the browser's own headers show it is not.
    production();
    expect(
      insecureCookieTransport(plainHttp("koda.example.com", { "sec-fetch-site": "same-origin" })),
    ).toBeNull();
    expect(
      insecureCookieTransport(plainHttp("koda.example.com", { "sec-fetch-mode": "navigate" })),
    ).toBeNull();
  });

  it("believes the browser's Origin over the forwarded scheme", () => {
    production();
    expect(
      insecureCookieTransport(plainHttp("koda.example.com", { origin: "https://koda.example.com" })),
    ).toBeNull();
    const proxied = new Headers({
      host: "koda.lan",
      "x-forwarded-proto": "https",
      origin: "http://koda.lan",
    });
    expect(insecureCookieTransport(proxied)).toEqual({ origin: "http://koda.lan" });
  });

  it("ignores an opaque Origin and falls back to the forwarded headers", () => {
    production();
    expect(insecureCookieTransport(plainHttp("10.0.0.5:3000", { origin: "null" }))).toEqual({
      origin: "http://10.0.0.5:3000",
    });
  });

  it("falls back to the request URL when no forwarded headers are present", () => {
    production();
    expect(
      insecureCookieTransport(new Headers(), new URL("http://192.168.1.10:3000/login")),
    ).toEqual({ origin: "http://192.168.1.10:3000" });
    expect(insecureCookieTransport(new Headers(), "https://192.168.1.10/login")).toBeNull();
  });

  it("reports nothing it cannot parse", () => {
    production();
    expect(insecureCookieTransport(plainHttp("bad host name"))).toBeNull();
    expect(insecureCookieTransport(new Headers({ host: "koda.lan", "x-forwarded-proto": "gopher" }))).toBeNull();
    expect(insecureCookieTransport(new Headers())).toBeNull();
  });

  it("reports nothing when cookies are not Secure", () => {
    vi.stubEnv("NODE_ENV", "development");
    expect(insecureCookieTransport(plainHttp("192.168.1.10:3000"))).toBeNull();
  });

  it("reports plain HTTP in development when SECURE_COOKIES forces Secure", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("SECURE_COOKIES", "true");
    expect(insecureCookieTransport(plainHttp("192.168.1.10:3000"))).toEqual({
      origin: "http://192.168.1.10:3000",
    });
  });
});
