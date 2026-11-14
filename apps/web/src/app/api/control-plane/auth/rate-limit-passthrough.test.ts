import fs from "node:fs";
import path from "node:path";

import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * ADR-038: the control plane's per-client buckets answer `429` with `Retry-After` the same
 * way whether or not the account exists, so the login, setup and recovery routes pass both
 * through. Every other failure, the per-account lockout included, keeps the route's own copy.
 */

const upstreamFetch = vi.fn();

vi.mock("@/lib/api-utils", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-utils")>();
  return { ...actual, upstreamFetch };
});

vi.mock("@/lib/request-origin", () => ({
  isTrustedDashboardRequest: () => true,
}));

type RouteCase = {
  path: string;
  body: Record<string, string>;
  load: () => Promise<{ POST: (request: NextRequest) => Promise<Response> }>;
  /** What the control plane answers for a rejected attempt on this route. */
  rejection: { status: number; error: string };
  /** What the route then shows the browser. */
  rejectedCopy: string;
};

const ROUTES: RouteCase[] = [
  {
    path: "login",
    body: { identifier: "owner@example.com", password: "a-strong-password-123" },
    load: () => import("./login/route"),
    // A locked account answers exactly like a wrong password.
    rejection: { status: 400, error: "Invalid credentials." },
    rejectedCopy: "Invalid credentials.",
  },
  {
    path: "register-owner",
    body: { email: "owner@example.com", password: "a-strong-password-123", bootstrap_code: "ABCD-EFGH-JKLM" },
    load: () => import("./register-owner/route"),
    rejection: { status: 400, error: "Setup code is invalid or expired." },
    rejectedCopy: "Setup code is invalid or expired.",
  },
  {
    path: "password/recover",
    body: { identifier: "owner@example.com", recovery_code: "ABCD-EFGH-JKLM", new_password: "a-strong-password-123" },
    load: () => import("./password/recover/route"),
    rejection: { status: 400, error: "Invalid identifier or recovery code." },
    rejectedCopy: "Invalid recovery details.",
  },
];

const THROTTLED_COPY = "Too many attempts. Try again later.";

function routeRequest(route: RouteCase): NextRequest {
  return new NextRequest(`http://127.0.0.1:3000/api/control-plane/auth/${route.path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(route.body),
  });
}

function throttled(headers: Record<string, string> = { "Retry-After": "60" }): Response {
  return new Response(JSON.stringify({ error: "rate limit exceeded" }), { status: 429, headers });
}

const cases = ROUTES.map((route) => [`POST /auth/${route.path}`, route] as const);

describe("auth routes pass the per-client rate limit through", () => {
  beforeEach(() => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("WEB_OPERATOR_SESSION_SECRET", "0123456789abcdef0123456789abcdef");
    upstreamFetch.mockReset();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.useRealTimers();
  });

  it.each(cases)("%s answers 429 with the control plane's Retry-After", async (_name, route) => {
    upstreamFetch.mockResolvedValue(throttled());
    const { POST } = await route.load();

    const response = await POST(routeRequest(route));
    const body = (await response.json()) as { error?: string };

    expect(response.status).toBe(429);
    expect(response.headers.get("Retry-After")).toBe("60");
    expect(response.headers.get("Cache-Control")).toBe("no-store");
    expect(body).toEqual({ error: THROTTLED_COPY });
  });

  it.each(cases)("%s sends an HTTP-date Retry-After on as seconds", async (_name, route) => {
    vi.useFakeTimers({ now: Date.UTC(2026, 10, 14, 12, 0, 0), toFake: ["Date"] });
    upstreamFetch.mockResolvedValue(throttled({ "Retry-After": "Sat, 14 Nov 2026 12:05:00 GMT" }));
    const { POST } = await route.load();

    const response = await POST(routeRequest(route));

    expect(response.status).toBe(429);
    expect(response.headers.get("Retry-After")).toBe("300");
  });

  it.each(cases)("%s answers 429 without a wait when the control plane names none", async (_name, route) => {
    upstreamFetch.mockResolvedValue(throttled({}));
    const { POST } = await route.load();

    const response = await POST(routeRequest(route));
    const body = (await response.json()) as { error?: string };

    expect(response.status).toBe(429);
    expect(response.headers.has("Retry-After")).toBe(false);
    expect(body).toEqual({ error: THROTTLED_COPY });
  });

  it.each(cases)("%s keeps a rejected attempt on its own copy", async (_name, route) => {
    upstreamFetch.mockResolvedValue(
      new Response(JSON.stringify({ error: route.rejection.error }), { status: route.rejection.status }),
    );
    const { POST } = await route.load();

    const response = await POST(routeRequest(route));
    const body = (await response.json()) as { error?: string };

    expect(response.status).toBe(route.rejection.status);
    expect(response.headers.has("Retry-After")).toBe(false);
    expect(body).toEqual({ error: route.rejectedCopy });
  });
});

describe("the auth screens rule in apps/web/CLAUDE.md", () => {
  const authRoutesRoot = path.join(process.cwd(), "src/app/api/control-plane/auth");

  function routesPassingTheRateLimitThrough(dir = authRoutesRoot, found: string[] = []): string[] {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        routesPassingTheRateLimitThrough(fullPath, found);
      } else if (entry.name === "route.ts" && fs.readFileSync(fullPath, "utf8").includes("rateLimitedAuthResponse(")) {
        found.push(path.relative(authRoutesRoot, dir).replaceAll(path.sep, "/"));
      }
    }
    return found.sort();
  }

  it("names exactly the routes and screens that show the wait", () => {
    const rule = fs
      .readFileSync(path.join(process.cwd(), "CLAUDE.md"), "utf8")
      .split("\n")
      .find((line) => line.includes("rateLimitedAuthResponse"));

    expect(routesPassingTheRateLimitThrough()).toEqual(ROUTES.map((route) => route.path).sort());
    expect(rule).toBeDefined();
    for (const route of ROUTES) {
      expect(rule).toContain(`auth/${route.path}`);
    }
    for (const screen of ["/login", "/setup", "/forgot-password"]) {
      expect(rule).toContain(`\`${screen}\``);
    }
    // The session routes behind /settings/account do not pass the 429 through.
    expect(rule).toContain("`/settings/account` does not show the wait yet");
    // Login and recovery fold every other failure into their own copy; setup passes the control
    // plane's setup error through, so the rule must not say all three keep a generic copy.
    const byPath = new Map(ROUTES.map((route) => [route.path, route]));
    const setup = byPath.get("register-owner")!;
    const recovery = byPath.get("password/recover")!;
    expect(setup.rejectedCopy).toBe(setup.rejection.error);
    expect(recovery.rejectedCopy).not.toBe(recovery.rejection.error);
    expect(rule).not.toContain("and keep every other upstream failure on their generic copy");
    expect(rule).toContain("Login and recovery keep every other upstream failure on their generic copy");
    expect(rule).toContain("`auth/register-owner` passes the control plane's own setup error text through");
  });
});
