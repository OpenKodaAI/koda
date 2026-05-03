import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { headersGet, redirectMock, getControlPlaneAuthStatusMock } = vi.hoisted(() => {
  return {
    headersGet: vi.fn<(name: string) => string | null>(() => null),
    redirectMock: vi.fn((target: string): never => {
      // Throwing mirrors what next/navigation does internally — stops
      // execution at the point of redirect so subsequent code never runs.
      const err = new Error(`NEXT_REDIRECT:${target}`);
      (err as Error & { __redirected?: string }).__redirected = target;
      throw err;
    }),
    getControlPlaneAuthStatusMock: vi.fn(),
  };
});

vi.mock("next/headers", () => ({
  headers: async () => ({
    get: headersGet,
  }),
}));
vi.mock("next/navigation", () => ({
  redirect: redirectMock,
}));
vi.mock("@/lib/control-plane", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/control-plane")>("@/lib/control-plane");
  return {
    ...actual,
    getControlPlaneAuthStatus: getControlPlaneAuthStatusMock,
  };
});

import { ControlPlaneRequestError } from "@/lib/control-plane";

beforeEach(() => {
  headersGet.mockReset().mockImplementation(() => null);
  redirectMock.mockClear();
  getControlPlaneAuthStatusMock.mockReset();
  vi.resetModules();
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function loadGuard() {
  // Re-import for each test so React's cache() is fresh per test run.
  return import("@/lib/auth-guard");
}

function captureRedirectTarget(): string | null {
  const call = redirectMock.mock.calls[0];
  return call ? (call[0] as string) : null;
}

describe("requireAuthenticatedSession", () => {
  it("returns the operator on success", async () => {
    headersGet.mockImplementation((name) =>
      name === "x-koda-pathname" ? "/sessions" : null,
    );
    getControlPlaneAuthStatusMock.mockResolvedValue({
      authenticated: true,
      has_owner: true,
      bootstrap_required: false,
      auth_mode: "session",
      session_required: true,
      recovery_available: true,
      operator: { id: "op_1", email: "owner@koda.dev", username: "owner", display_name: "Owner" },
    });

    const { requireAuthenticatedSession } = await loadGuard();
    const result = await requireAuthenticatedSession();
    expect(result.operator.email).toBe("owner@koda.dev");
    expect(redirectMock).not.toHaveBeenCalled();
  });

  it("redirects to /login?next= when not authenticated", async () => {
    headersGet.mockImplementation((name) =>
      name === "x-koda-pathname" ? "/sessions/abc" : null,
    );
    getControlPlaneAuthStatusMock.mockResolvedValue({
      authenticated: false,
      has_owner: true,
      bootstrap_required: false,
      auth_mode: "session",
      session_required: true,
      recovery_available: false,
      operator: null,
    });

    const { requireAuthenticatedSession } = await loadGuard();
    await expect(requireAuthenticatedSession()).rejects.toThrow(/NEXT_REDIRECT/);
    expect(captureRedirectTarget()).toBe(`/login?next=${encodeURIComponent("/sessions/abc")}`);
  });

  it("redirects to /login on 401 ControlPlaneRequestError", async () => {
    headersGet.mockImplementation(() => null);
    getControlPlaneAuthStatusMock.mockRejectedValue(
      new ControlPlaneRequestError("Unauthorized", 401),
    );

    const { requireAuthenticatedSession } = await loadGuard();
    await expect(requireAuthenticatedSession()).rejects.toThrow(/NEXT_REDIRECT/);
    expect(captureRedirectTarget()).toBe("/login");
  });

  it("propagates 5xx upstream errors instead of looping", async () => {
    getControlPlaneAuthStatusMock.mockRejectedValue(
      new ControlPlaneRequestError("Upstream down", 503),
    );

    const { requireAuthenticatedSession } = await loadGuard();
    await expect(requireAuthenticatedSession()).rejects.toThrow(/Upstream down/);
    expect(redirectMock).not.toHaveBeenCalled();
  });

  it("ignores unsafe x-koda-pathname when building the next param", async () => {
    headersGet.mockImplementation((name) =>
      name === "x-koda-pathname" ? "//evil.com" : null,
    );
    getControlPlaneAuthStatusMock.mockResolvedValue({
      authenticated: false,
      has_owner: true,
      bootstrap_required: false,
      auth_mode: "session",
      session_required: true,
      recovery_available: false,
      operator: null,
    });

    const { requireAuthenticatedSession } = await loadGuard();
    await expect(requireAuthenticatedSession()).rejects.toThrow(/NEXT_REDIRECT/);
    expect(captureRedirectTarget()).toBe("/login");
  });
});

describe("getOptionalAuthStatus", () => {
  it("returns null on ControlPlaneRequestError", async () => {
    getControlPlaneAuthStatusMock.mockRejectedValue(
      new ControlPlaneRequestError("Unauthorized", 401),
    );
    const { getOptionalAuthStatus } = await loadGuard();
    expect(await getOptionalAuthStatus()).toBeNull();
  });

  it("propagates non-ControlPlaneRequestError failures", async () => {
    getControlPlaneAuthStatusMock.mockRejectedValue(new Error("network blew up"));
    const { getOptionalAuthStatus } = await loadGuard();
    await expect(getOptionalAuthStatus()).rejects.toThrow(/network blew up/);
  });
});

describe("resolveOptionalAuthStatus", () => {
  it("returns ok with the status payload on success", async () => {
    getControlPlaneAuthStatusMock.mockResolvedValue({
      authenticated: true,
      has_owner: true,
      bootstrap_required: false,
      auth_mode: "session",
      session_required: true,
      recovery_available: true,
      operator: { id: "op_1", email: "owner@koda.dev", username: "owner", display_name: "Owner" },
    });

    const { resolveOptionalAuthStatus } = await loadGuard();
    const result = await resolveOptionalAuthStatus();
    expect(result.kind).toBe("ok");
    if (result.kind === "ok") {
      expect(result.status.authenticated).toBe(true);
    }
  });

  it("returns 'unauthenticated' on a 401 from upstream", async () => {
    getControlPlaneAuthStatusMock.mockRejectedValue(
      new ControlPlaneRequestError("Unauthorized", 401),
    );
    const { resolveOptionalAuthStatus } = await loadGuard();
    const result = await resolveOptionalAuthStatus();
    expect(result.kind).toBe("unauthenticated");
  });

  it("returns 'unreachable' on a 503 from upstream — does NOT collapse to a logout", async () => {
    getControlPlaneAuthStatusMock.mockRejectedValue(
      new ControlPlaneRequestError("Control plane unavailable", 503),
    );
    const { resolveOptionalAuthStatus } = await loadGuard();
    const result = await resolveOptionalAuthStatus();
    expect(result.kind).toBe("unreachable");
  });

  it("propagates non-ControlPlaneRequestError failures", async () => {
    getControlPlaneAuthStatusMock.mockRejectedValue(new Error("boom"));
    const { resolveOptionalAuthStatus } = await loadGuard();
    await expect(resolveOptionalAuthStatus()).rejects.toThrow(/boom/);
  });
});
