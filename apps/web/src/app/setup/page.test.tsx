import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";

const {
  cookieValues,
  requestHeaders,
  getControlPlaneAuthStatusMock,
  redirectMock,
  setupScreenMock,
  insecureTransportScreenMock,
} = vi.hoisted(() => {
  return {
    cookieValues: new Map<string, string>(),
    requestHeaders: { current: new Headers() },
    getControlPlaneAuthStatusMock: vi.fn(),
    redirectMock: vi.fn((target: string): never => {
      const error = new Error(`NEXT_REDIRECT:${target}`);
      (error as Error & { __redirected?: string }).__redirected = target;
      throw error;
    }),
    setupScreenMock: vi.fn(() => <div data-testid="setup-screen" />),
    insecureTransportScreenMock: vi.fn(() => <div data-testid="insecure-transport-screen" />),
  };
});

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) => {
      const value = cookieValues.get(name);
      return value === undefined ? undefined : { value };
    },
  }),
  headers: async () => requestHeaders.current,
}));

vi.mock("next/navigation", () => ({
  redirect: redirectMock,
}));

vi.mock("@/components/setup/setup-screen", () => ({
  SetupScreen: setupScreenMock,
}));

vi.mock("@/components/auth/insecure-transport-screen", () => ({
  InsecureTransportScreen: insecureTransportScreenMock,
}));

vi.mock("@/lib/control-plane", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/control-plane")>("@/lib/control-plane");
  return {
    ...actual,
    getControlPlaneAuthStatus: getControlPlaneAuthStatusMock,
  };
});

import SetupPage from "@/app/setup/page";
import { ControlPlaneRequestError } from "@/lib/control-plane";
import { OWNER_EXISTS_HINT_COOKIE } from "@/lib/web-operator-session-constants";

function setupProps(next: string | undefined = "/") {
  return {
    searchParams: Promise.resolve(next ? { next } : {}),
  };
}

beforeEach(() => {
  cookieValues.clear();
  requestHeaders.current = new Headers();
  getControlPlaneAuthStatusMock.mockReset();
  redirectMock.mockClear();
  setupScreenMock.mockClear();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("SetupPage", () => {
  it("explains that HTTPS is required before the setup code can be spent over plain HTTP (J-14)", async () => {
    vi.stubEnv("NODE_ENV", "production");
    requestHeaders.current = new Headers({
      host: "192.168.1.10:3000",
      "x-forwarded-host": "192.168.1.10:3000",
      "x-forwarded-proto": "http",
    });

    const result = (await SetupPage(setupProps("/"))) as ReactElement<{ origin: string }>;

    // No redirect to /login and no auth probe: the page that explains is the
    // last stop, so the operator is not bounced between /setup and /login.
    expect(result.type).toBe(insecureTransportScreenMock);
    expect(result.props.origin).toBe("http://192.168.1.10:3000");
    expect(redirectMock).not.toHaveBeenCalled();
    expect(getControlPlaneAuthStatusMock).not.toHaveBeenCalled();
    expect(setupScreenMock).not.toHaveBeenCalled();
  });

  it("redirects returning users to login when the control plane reports an owner", async () => {
    getControlPlaneAuthStatusMock.mockResolvedValue({
      authenticated: false,
      has_owner: true,
      bootstrap_required: false,
      auth_mode: "local_account",
      session_required: true,
      recovery_available: true,
      operator: null,
    });

    await expect(SetupPage(setupProps("/executions"))).rejects.toThrow(/NEXT_REDIRECT/);

    expect(getControlPlaneAuthStatusMock).toHaveBeenCalledWith({ timeoutMs: 5000 });
    expect(redirectMock).toHaveBeenCalledWith("/login?next=%2Fexecutions");
    expect(setupScreenMock).not.toHaveBeenCalled();
  });

  it("uses the owner hint cookie to avoid showing setup when the status probe is unavailable", async () => {
    cookieValues.set(OWNER_EXISTS_HINT_COOKIE, "1");
    getControlPlaneAuthStatusMock.mockRejectedValue(
      new ControlPlaneRequestError("Control plane did not respond", 503),
    );

    await expect(SetupPage(setupProps("/"))).rejects.toThrow(/NEXT_REDIRECT/);

    expect(redirectMock).toHaveBeenCalledWith("/login?next=%2F");
    expect(setupScreenMock).not.toHaveBeenCalled();
  });

  it("trusts a fresh no-owner response over a stale owner hint cookie", async () => {
    cookieValues.set(OWNER_EXISTS_HINT_COOKIE, "1");
    getControlPlaneAuthStatusMock.mockResolvedValue({
      authenticated: false,
      has_owner: false,
      bootstrap_required: true,
      auth_mode: "local_account",
      session_required: false,
      recovery_available: false,
      operator: null,
    });

    const result = (await SetupPage(setupProps(undefined))) as ReactElement<{
      authStatus: { has_owner: boolean };
    }>;

    expect(redirectMock).not.toHaveBeenCalled();
    expect(result.type).toBe(setupScreenMock);
    expect(result.props.authStatus.has_owner).toBe(false);
  });
});
