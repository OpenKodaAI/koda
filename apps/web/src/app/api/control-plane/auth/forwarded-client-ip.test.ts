import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Every auth route that calls the control plane forwards the browser's address,
 * so the control plane rate limits each client separately instead of charging
 * all of them to the dashboard's own bucket.
 */

const upstreamFetch = vi.fn();

vi.mock("@/lib/api-utils", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-utils")>();
  return { ...actual, upstreamFetch };
});

vi.mock("@/lib/request-origin", () => ({
  isTrustedDashboardRequest: () => true,
}));

vi.mock("@/lib/web-operator-session", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/web-operator-session")>();
  return { ...actual, getWebOperatorTokenFromCookie: vi.fn(async () => "operator-token") };
});

type RouteCase = {
  path: string;
  method: "GET" | "POST";
  body?: Record<string, string>;
  load: () => Promise<Record<string, unknown>>;
  /** logout calls fetch directly instead of upstreamFetch. */
  viaGlobalFetch?: boolean;
};

const ROUTES: RouteCase[] = [
  {
    path: "login",
    method: "POST",
    body: { identifier: "owner@example.com", password: "a-strong-password-123" },
    load: () => import("./login/route"),
  },
  { path: "logout", method: "POST", load: () => import("./logout/route"), viaGlobalFetch: true },
  {
    path: "password/change",
    method: "POST",
    body: { current_password: "an-old-password-123", new_password: "a-strong-password-123" },
    load: () => import("./password/change/route"),
  },
  {
    path: "password/recover",
    method: "POST",
    body: { identifier: "owner@example.com", recovery_code: "ABCD-EFGH-JKLM", new_password: "a-strong-password-123" },
    load: () => import("./password/recover/route"),
  },
  { path: "recovery-codes", method: "GET", load: () => import("./recovery-codes/route") },
  {
    path: "recovery-codes/regenerate",
    method: "POST",
    body: { current_password: "a-strong-password-123" },
    load: () => import("./recovery-codes/regenerate/route"),
  },
];

function okResponse(): Response {
  return new Response(JSON.stringify({ ok: true, session_token: "session-token", recovery_codes: ["code-1"] }), {
    status: 200,
  });
}

describe("auth routes forward the browser address to the control plane", () => {
  const globalFetch = vi.fn();

  beforeEach(() => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("WEB_OPERATOR_SESSION_SECRET", "0123456789abcdef0123456789abcdef");
    upstreamFetch.mockReset();
    upstreamFetch.mockImplementation(async () => okResponse());
    globalFetch.mockReset();
    globalFetch.mockImplementation(async () => okResponse());
    vi.stubGlobal("fetch", globalFetch);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  const cases = ROUTES.map((route) => [`${route.method} /auth/${route.path}`, route] as const);

  it.each(cases)("%s", async (_name, route) => {
    const handlers = await route.load();
    const handler = handlers[route.method] as (request: NextRequest) => Promise<Response>;
    const request = new NextRequest(`http://127.0.0.1:3000/api/control-plane/auth/${route.path}`, {
      method: route.method,
      // server.mjs writes a single address; a spoofed entry to its left is still ignored.
      headers: { "Content-Type": "application/json", "X-Forwarded-For": "10.9.9.9, 198.51.100.7" },
      body: route.body ? JSON.stringify(route.body) : undefined,
    });

    await handler(request);

    const calls = (route.viaGlobalFetch ? globalFetch : upstreamFetch).mock.calls;
    expect(calls).toHaveLength(1);
    const init = calls[0]?.[1] as RequestInit | undefined;
    expect(new Headers(init?.headers).get("X-Forwarded-For")).toBe("198.51.100.7");
  });
});
