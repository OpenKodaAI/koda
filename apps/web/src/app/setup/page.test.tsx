import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";

const {
  cookieValues,
  getControlPlaneAuthStatusMock,
  redirectMock,
  setupScreenMock,
} = vi.hoisted(() => {
  return {
    cookieValues: new Map<string, string>(),
    getControlPlaneAuthStatusMock: vi.fn(),
    redirectMock: vi.fn((target: string): never => {
      const error = new Error(`NEXT_REDIRECT:${target}`);
      (error as Error & { __redirected?: string }).__redirected = target;
      throw error;
    }),
    setupScreenMock: vi.fn(() => <div data-testid="setup-screen" />),
  };
});

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) => {
      const value = cookieValues.get(name);
      return value === undefined ? undefined : { value };
    },
  }),
}));

vi.mock("next/navigation", () => ({
  redirect: redirectMock,
}));

vi.mock("@/components/setup/setup-screen", () => ({
  SetupScreen: setupScreenMock,
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
  getControlPlaneAuthStatusMock.mockReset();
  redirectMock.mockClear();
  setupScreenMock.mockClear();
});

describe("SetupPage", () => {
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
