import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";

const {
  requestHeaders,
  getControlPlaneAuthStatusMock,
  redirectMock,
  forgotPasswordScreenMock,
  insecureTransportScreenMock,
} = vi.hoisted(() => ({
  requestHeaders: { current: new Headers() },
  getControlPlaneAuthStatusMock: vi.fn(),
  redirectMock: vi.fn((target: string): never => {
    throw new Error(`NEXT_REDIRECT:${target}`);
  }),
  forgotPasswordScreenMock: vi.fn(() => <div data-testid="forgot-password-screen" />),
  insecureTransportScreenMock: vi.fn(() => <div data-testid="insecure-transport-screen" />),
}));

vi.mock("next/headers", () => ({
  headers: async () => requestHeaders.current,
}));

vi.mock("next/navigation", () => ({
  redirect: redirectMock,
}));

vi.mock("@/components/auth/forgot-password-screen", () => ({
  ForgotPasswordScreen: forgotPasswordScreenMock,
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

import ForgotPasswordPage from "@/app/forgot-password/page";

function forgotProps(next?: string) {
  return { searchParams: Promise.resolve(next ? { next } : {}) };
}

beforeEach(() => {
  requestHeaders.current = new Headers();
  getControlPlaneAuthStatusMock.mockReset();
  getControlPlaneAuthStatusMock.mockResolvedValue({ authenticated: false, has_owner: true });
  redirectMock.mockClear();
  vi.stubEnv("NODE_ENV", "production");
  vi.spyOn(console, "warn").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("ForgotPasswordPage", () => {
  it("explains that HTTPS is required instead of taking a recovery code over plain HTTP (J-14)", async () => {
    requestHeaders.current = new Headers({
      host: "192.168.1.10:3000",
      "x-forwarded-host": "192.168.1.10:3000",
      "x-forwarded-proto": "http",
    });

    const result = (await ForgotPasswordPage(forgotProps("/executions"))) as ReactElement<{
      origin: string;
    }>;

    // The recovery code and the new password would cross the network in clear
    // text, and the reset would end on a /login that cannot sign in here.
    expect(result.type).toBe(insecureTransportScreenMock);
    expect(result.props.origin).toBe("http://192.168.1.10:3000");
    expect(redirectMock).not.toHaveBeenCalled();
    expect(getControlPlaneAuthStatusMock).not.toHaveBeenCalled();
  });

  it("shows the recovery form over HTTPS and on a loopback address", async () => {
    requestHeaders.current = new Headers({
      host: "koda.example.com",
      "x-forwarded-host": "koda.example.com",
      "x-forwarded-proto": "https",
    });
    expect(((await ForgotPasswordPage(forgotProps())) as ReactElement).type).toBe(
      forgotPasswordScreenMock,
    );

    requestHeaders.current = new Headers({
      host: "127.0.0.1:3000",
      "x-forwarded-host": "127.0.0.1:3000",
      "x-forwarded-proto": "http",
    });
    expect(((await ForgotPasswordPage(forgotProps())) as ReactElement).type).toBe(
      forgotPasswordScreenMock,
    );
  });
});
