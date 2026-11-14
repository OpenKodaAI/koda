import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  INSECURE_TRANSPORT_LOG_INTERVAL_MS,
  INSECURE_TRANSPORT_LOG_MAX_ORIGINS,
  insecureCookieTransport,
  insecureCookieTransportResponse,
  isLoopbackHostname,
  secureCookiesEnabled,
} from "@/lib/cookie-transport";

// Where insecureCookieTransport() keeps its logging window, shared by every
// bundle of the module in one process.
const LOG_STATE_KEY = Symbol.for("koda.web.insecure-cookie-transport-log-window");
type LogStateHost = typeof globalThis & { [LOG_STATE_KEY]?: unknown };
let savedLogState: unknown;

beforeEach(() => {
  // A developer or CI shell may export either switch; every test sets the one it needs.
  vi.stubEnv("SECURE_COOKIES", "");
  vi.stubEnv("ALLOW_INSECURE_COOKIES", "");
  // Start each test with nothing logged, and keep its warnings out of the output.
  const host = globalThis as LogStateHost;
  savedLogState = host[LOG_STATE_KEY];
  delete host[LOG_STATE_KEY];
  vi.spyOn(console, "warn").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  vi.useRealTimers();
  const host = globalThis as LogStateHost;
  if (savedLogState === undefined) delete host[LOG_STATE_KEY];
  else host[LOG_STATE_KEY] = savedLogState;
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
  // A trailing dot names the same host; URL keeps it in `hostname`.
  it.each(["localhost", "LOCALHOST", "localhost.", "koda.localhost", "koda.localhost.", "127.0.0.1", "127.8.9.10", "[::1]"])(
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

  it.each(["localhost:3000", "localhost.:3000", "127.0.0.1:3000", "[::1]:3000", "koda.localhost:3000"])(
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

  it("believes Fetch Metadata over an Origin that a proxy rewrote to its plain-HTTP upstream", () => {
    // A browser on https://koda.example.com behind a proxy that sets
    // `Origin $scheme://$host` for its upstream. Only a browser sends
    // Sec-Fetch-*, and only to a URL it treats as secure, so it keeps the
    // Secure cookies whatever the rewritten Origin says.
    production();
    const signIn = new Headers({
      host: "koda-web:3000",
      origin: "http://koda-web:3000",
      "x-forwarded-proto": "https",
      "sec-fetch-site": "same-origin",
      "sec-fetch-mode": "cors",
    });
    expect(insecureCookieTransport(signIn)).toBeNull();
    expect(
      insecureCookieTransport(
        new Headers({ host: "192.168.1.10:3000", origin: "http://192.168.1.10:3000", "sec-fetch-site": "same-origin" }),
      ),
    ).toBeNull();
    // The page that shows the form agrees with the route that takes it.
    const navigation = new Headers({
      host: "koda-web:3000",
      "x-forwarded-proto": "https",
      "sec-fetch-site": "none",
      "sec-fetch-mode": "navigate",
    });
    expect(insecureCookieTransport(navigation)).toBeNull();
    expect(console.warn).not.toHaveBeenCalled();
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

describe("insecureCookieTransportResponse", () => {
  it("refuses with INSECURE_TRANSPORT, names the origin and is never cached", async () => {
    const response = insecureCookieTransportResponse({ origin: "http://192.168.1.10:3000" });
    const body = (await response.json()) as { error: { code: string; message: string; user_action: string } };

    expect(response.status).toBe(403);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("set-cookie")).toBeNull();
    expect(body.error.code).toBe("INSECURE_TRANSPORT");
    expect(body.error.message).toContain("http://192.168.1.10:3000");
    expect(body.error.user_action).toMatch(/HTTPS/);
  });
});

describe("the [cookie-transport] warning", () => {
  function warnings(): string[] {
    return vi.mocked(console.warn).mock.calls.map((call) => call.map(String).join(" "));
  }

  it("is logged once for an origin, naming it, however many requests it makes", () => {
    production();
    insecureCookieTransport(plainHttp("192.168.1.10:3000"));
    insecureCookieTransport(plainHttp("192.168.1.10:3000"));

    expect(warnings()).toHaveLength(1);
    expect(warnings()[0]).toContain("[cookie-transport]");
    expect(warnings()[0]).toContain("http://192.168.1.10:3000");
  });

  it("is logged for each origin, so a scanner's spoofed Host does not hide the operator's address", () => {
    production();
    insecureCookieTransport(plainHttp("scanner.example:3000"));
    insecureCookieTransport(plainHttp("192.168.1.10:3000"));
    insecureCookieTransport(plainHttp("scanner.example:3000"));

    expect(warnings()).toHaveLength(2);
    expect(warnings()[0]).toContain("http://scanner.example:3000");
    expect(warnings()[1]).toContain("http://192.168.1.10:3000");
  });

  it("is logged again for an origin after the interval", () => {
    production();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-14T12:00:00Z"));
    insecureCookieTransport(plainHttp("192.168.1.10:3000"));

    vi.advanceTimersByTime(INSECURE_TRANSPORT_LOG_INTERVAL_MS - 1);
    insecureCookieTransport(plainHttp("192.168.1.10:3000"));
    expect(warnings()).toHaveLength(1);

    vi.advanceTimersByTime(1);
    insecureCookieTransport(plainHttp("192.168.1.10:3000"));
    expect(warnings()).toHaveLength(2);
  });

  it("names a bounded number of origins per interval, then says the rest are counted but not named", () => {
    production();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-14T12:00:00Z"));
    // A scanner's made-up hosts, one port each, use up every named line of the interval.
    for (let index = 0; index < INSECURE_TRANSPORT_LOG_MAX_ORIGINS; index += 1) {
      expect(insecureCookieTransport(plainHttp(`scan.invalid:${4000 + index}`))).toEqual({
        origin: `http://scan.invalid:${4000 + index}`,
      });
    }
    expect(warnings()).toHaveLength(INSECURE_TRANSPORT_LOG_MAX_ORIGINS);

    // The operator's own address comes next: still refused and not named, but
    // the log says that from here on addresses are only counted.
    vi.advanceTimersByTime(10 * 60 * 1000);
    expect(insecureCookieTransport(plainHttp("10.0.0.5:3000"))).toEqual({ origin: "http://10.0.0.5:3000" });
    expect(warnings()).toHaveLength(INSECURE_TRANSPORT_LOG_MAX_ORIGINS + 1);
    expect(warnings().at(-1)).toBe(
      `[cookie-transport] More than ${INSECURE_TRANSPORT_LOG_MAX_ORIGINS} addresses opened the dashboard over plain HTTP since 2026-11-14T12:00:00.000Z. Further addresses are still refused, but not named before 2026-11-14T13:00:00.000Z; the first plain-HTTP request after that logs how many requests went unnamed.`,
    );

    // One such line per interval, however many more requests and origins follow.
    expect(insecureCookieTransport(plainHttp("10.0.0.5:3000"))).toEqual({ origin: "http://10.0.0.5:3000" });
    expect(insecureCookieTransport(plainHttp("scan.invalid:5000"))).toEqual({ origin: "http://scan.invalid:5000" });
    insecureCookieTransport(plainHttp("scan.invalid:4000"));
    expect(warnings()).toHaveLength(INSECURE_TRANSPORT_LOG_MAX_ORIGINS + 1);

    // The first request after the interval reports the count, then is named itself.
    vi.advanceTimersByTime(INSECURE_TRANSPORT_LOG_INTERVAL_MS - 10 * 60 * 1000);
    insecureCookieTransport(plainHttp("192.168.1.10:3000"));
    expect(warnings()).toHaveLength(INSECURE_TRANSPORT_LOG_MAX_ORIGINS + 3);
    expect(warnings().at(-2)).toBe(
      "[cookie-transport] 3 plain-HTTP requests from addresses that were not named were refused between 2026-11-14T12:00:00.000Z and 2026-11-14T13:00:00.000Z.",
    );
    expect(warnings().at(-1)).toContain("http://192.168.1.10:3000");

    // An interval that names every address reports no count.
    vi.advanceTimersByTime(INSECURE_TRANSPORT_LOG_INTERVAL_MS);
    insecureCookieTransport(plainHttp("192.168.1.10:3000"));
    expect(warnings()).toHaveLength(INSECURE_TRANSPORT_LOG_MAX_ORIGINS + 4);
    expect(warnings().at(-1)).toContain("http://192.168.1.10:3000");
  });

  it("counts a single unnamed request in the singular", () => {
    production();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-14T12:00:00Z"));
    for (let index = 0; index <= INSECURE_TRANSPORT_LOG_MAX_ORIGINS; index += 1) {
      insecureCookieTransport(plainHttp(`scan.invalid:${4000 + index}`));
    }
    vi.advanceTimersByTime(INSECURE_TRANSPORT_LOG_INTERVAL_MS);
    insecureCookieTransport(plainHttp("192.168.1.10:3000"));

    expect(warnings().at(-2)).toBe(
      "[cookie-transport] 1 plain-HTTP request from an address that was not named was refused between 2026-11-14T12:00:00.000Z and 2026-11-14T13:00:00.000Z.",
    );
  });

  it("is not logged for a request whose browser keeps the cookies", () => {
    production();
    insecureCookieTransport(plainHttp("127.0.0.1:3000"));
    insecureCookieTransport(plainHttp("koda.example.com", { origin: "https://koda.example.com" }));

    expect(warnings()).toHaveLength(0);
  });
});
