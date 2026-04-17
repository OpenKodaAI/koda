import { describe, expect, it } from "vitest";

import { isTrustedDashboardRequest } from "./request-origin";

function makeRequest(
  url: string,
  init: RequestInit & { headers?: Record<string, string> } = {},
): Request {
  return new Request(url, init);
}

describe("isTrustedDashboardRequest", () => {
  it("allows same-origin mutations when Origin matches the request URL", () => {
    const request = makeRequest("http://localhost/api/thing", {
      method: "POST",
      headers: { Origin: "http://localhost" },
    });
    expect(isTrustedDashboardRequest(request)).toBe(true);
  });

  it("blocks mutations from a cross-origin attacker", () => {
    const request = makeRequest("http://localhost/api/thing", {
      method: "POST",
      headers: { Origin: "http://evil.example.com" },
    });
    expect(isTrustedDashboardRequest(request)).toBe(false);
  });

  it("allows safe GETs regardless of Origin", () => {
    const request = makeRequest("http://localhost/api/thing", {
      method: "GET",
    });
    expect(isTrustedDashboardRequest(request)).toBe(true);
  });

  it("allows the browser's Origin when the server bound to 0.0.0.0 but the client addressed the host by its loopback name", () => {
    // Next.js middleware sees `request.nextUrl.origin === "http://0.0.0.0:3000"`
    // because the server is bound to 0.0.0.0, but the browser reached it via
    // http://127.0.0.1:3000. The Host header is the source of truth for what
    // the client actually contacted; trusting the server's bind origin here
    // blocks every legitimate same-origin mutation.
    const request = makeRequest("http://0.0.0.0:3000/api/thing", {
      method: "POST",
      headers: {
        Host: "127.0.0.1:3000",
        Origin: "http://127.0.0.1:3000",
      },
    });
    expect(isTrustedDashboardRequest(request)).toBe(true);
  });

  it("still blocks cross-origin requests even when the Host header matches", () => {
    const request = makeRequest("http://0.0.0.0:3000/api/thing", {
      method: "POST",
      headers: {
        Host: "127.0.0.1:3000",
        Origin: "http://evil.example.com",
      },
    });
    expect(isTrustedDashboardRequest(request)).toBe(false);
  });
});
