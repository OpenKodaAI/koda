import type { IncomingMessage } from "node:http";
import { describe, expect, it } from "vitest";
import {
  defaultGatewayFromRouteTable,
  normalizeAddress,
  parseTrustedProxies,
  resolveClientAddress,
  rewriteForwardedFor,
} from "./forwarded-for.mjs";

const ROUTE_TABLE = [
  "Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT",
  "eth0\t00000000\t010012AC\t0003\t0\t0\t0\t00000000\t0\t0\t0",
  "eth0\t000012AC\t00000000\t0001\t0\t0\t0\t0000FFFF\t0\t0\t0",
].join("\n");

function incoming(remoteAddress: string | undefined, headers: Record<string, string> = {}): IncomingMessage {
  return { socket: { remoteAddress }, headers: { ...headers } } as unknown as IncomingMessage;
}

describe("rewriteForwardedFor", () => {
  const { isTrusted } = parseTrustedProxies("", { gateway: () => null });

  it("replaces a header sent by a client that reached the dashboard directly", () => {
    // Next.js only fills x-forwarded-for when it is missing, so without the
    // rewrite this value would choose the client's rate-limit bucket.
    const request = incoming("203.0.113.7", { "x-forwarded-for": "198.51.100.1" });

    rewriteForwardedFor(request, isTrusted);

    expect(request.headers["x-forwarded-for"]).toBe("203.0.113.7");
  });

  it("does not let a direct client choose the shared bucket with an empty or malformed header", () => {
    for (const forwardedFor of ["", " , ", "not-an-ip", "127.0.0.1"]) {
      const request = incoming("203.0.113.7", { "x-forwarded-for": forwardedFor });
      rewriteForwardedFor(request, isTrusted);
      expect(request.headers["x-forwarded-for"]).toBe("203.0.113.7");
    }
  });

  it("keeps the client a trusted proxy reports and drops what is to its left", () => {
    const request = incoming("127.0.0.1", { "x-forwarded-for": "10.9.9.9, 198.51.100.7" });

    rewriteForwardedFor(request, isTrusted);

    expect(request.headers["x-forwarded-for"]).toBe("198.51.100.7");
  });

  it("uses the peer itself when a trusted proxy sends no header", () => {
    const request = incoming("::ffff:127.0.0.1");

    rewriteForwardedFor(request, isTrusted);

    expect(request.headers["x-forwarded-for"]).toBe("127.0.0.1");
  });

  it("removes the header when the socket has no peer address", () => {
    const request = incoming(undefined, { "x-forwarded-for": "198.51.100.1" });

    rewriteForwardedFor(request, isTrusted);

    expect(request.headers["x-forwarded-for"]).toBeUndefined();
  });
});

describe("resolveClientAddress", () => {
  const { isTrusted } = parseTrustedProxies("172.18.0.0/16", { gateway: () => null });

  it("walks trusted hops from the right", () => {
    expect(resolveClientAddress("127.0.0.1", "10.0.0.9, 198.51.100.4, 172.18.0.5", isTrusted)).toBe("198.51.100.4");
  });

  it("stops at an unparseable hop", () => {
    expect(resolveClientAddress("127.0.0.1", "198.51.100.4, bogus", isTrusted)).toBe("127.0.0.1");
  });

  it("joins repeated headers", () => {
    expect(resolveClientAddress("127.0.0.1", ["10.0.0.9", "198.51.100.4"], isTrusted)).toBe("198.51.100.4");
  });
});

describe("parseTrustedProxies", () => {
  it("always trusts loopback and nothing else by default", () => {
    const proxies = parseTrustedProxies(undefined, { gateway: () => "172.18.0.1" });

    expect(proxies.isTrusted("127.0.0.1")).toBe(true);
    expect(proxies.isTrusted("::1")).toBe(true);
    expect(proxies.isTrusted("172.18.0.1")).toBe(false);
    expect(proxies.isTrusted("10.0.0.1")).toBe(false);
  });

  it("accepts IPs, CIDRs and the Docker gateway", () => {
    const proxies = parseTrustedProxies("gateway, 10.1.2.3, 192.168.0.0/16, 2001:db8::/32", {
      gateway: () => "172.18.0.1",
    });

    expect(proxies.isTrusted("172.18.0.1")).toBe(true);
    expect(proxies.isTrusted("172.18.0.2")).toBe(false);
    expect(proxies.isTrusted("10.1.2.3")).toBe(true);
    expect(proxies.isTrusted("192.168.40.1")).toBe(true);
    expect(proxies.isTrusted("2001:db8:1::1")).toBe(true);
    expect(proxies.trusted).toContain("172.18.0.1 (gateway)");
    expect(proxies.ignored).toEqual([]);
  });

  it("reports entries it cannot use instead of trusting them", () => {
    const proxies = parseTrustedProxies("10.0.0.0/33, web, 10.0.0.1/8/1, gateway", { gateway: () => null });

    expect(proxies.ignored).toEqual(["10.0.0.0/33", "web", "10.0.0.1/8/1", "gateway"]);
    expect(proxies.isTrusted("10.0.0.1")).toBe(false);
  });
});

describe("defaultGatewayFromRouteTable", () => {
  it("reads the default route's gateway in host byte order", () => {
    expect(defaultGatewayFromRouteTable(ROUTE_TABLE, "LE")).toBe("172.18.0.1");
    expect(defaultGatewayFromRouteTable(ROUTE_TABLE.replace("010012AC", "AC120001"), "BE")).toBe("172.18.0.1");
  });

  it("returns null without a default route", () => {
    expect(defaultGatewayFromRouteTable(ROUTE_TABLE.split("\n").filter((line) => !line.includes("0003")).join("\n"))).toBeNull();
    expect(defaultGatewayFromRouteTable("")).toBeNull();
  });
});

describe("normalizeAddress", () => {
  it("canonicalizes IPv4-mapped and upper-case IPv6 addresses", () => {
    expect(normalizeAddress("::FFFF:192.0.2.1")).toBe("192.0.2.1");
    expect(normalizeAddress(" 2001:DB8::1 ")).toBe("2001:db8::1");
    expect(normalizeAddress("example.com")).toBeNull();
    expect(normalizeAddress(undefined)).toBeNull();
  });
});
