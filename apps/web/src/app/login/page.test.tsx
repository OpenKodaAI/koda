import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";

const {
  cookieValues,
  requestHeaders,
  getControlPlaneAuthStatusMock,
  redirectMock,
  loginScreenMock,
  insecureTransportScreenMock,
} = vi.hoisted(() => ({
  cookieValues: new Map<string, string>(),
  requestHeaders: { current: new Headers() },
  getControlPlaneAuthStatusMock: vi.fn(),
  redirectMock: vi.fn((target: string): never => {
    throw new Error(`NEXT_REDIRECT:${target}`);
  }),
  loginScreenMock: vi.fn(() => <div data-testid="login-screen" />),
  insecureTransportScreenMock: vi.fn(() => <div data-testid="insecure-transport-screen" />),
}));

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

vi.mock("@/components/auth/login-screen", () => ({
  LoginScreen: loginScreenMock,
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

import LoginPage from "@/app/login/page";
import { WEB_OPERATOR_SESSION_COOKIE } from "@/lib/web-operator-session-constants";

function loginProps(next?: string) {
  return { searchParams: Promise.resolve(next ? { next } : {}) };
}

beforeEach(() => {
  cookieValues.clear();
  requestHeaders.current = new Headers();
  getControlPlaneAuthStatusMock.mockReset();
  redirectMock.mockClear();
  vi.stubEnv("NODE_ENV", "production");
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("LoginPage", () => {
  it("explains that HTTPS is required instead of showing a form whose session would be dropped (J-14)", async () => {
    requestHeaders.current = new Headers({
      host: "192.168.1.10:3000",
      "x-forwarded-host": "192.168.1.10:3000",
      "x-forwarded-proto": "http",
    });
    // A stale non-Secure cookie must not send the page through the auth probe.
    cookieValues.set(WEB_OPERATOR_SESSION_COOKIE, "sealed");

    const result = (await LoginPage(loginProps("/executions"))) as ReactElement<{ origin: string }>;

    expect(result.type).toBe(insecureTransportScreenMock);
    expect(result.props.origin).toBe("http://192.168.1.10:3000");
    expect(redirectMock).not.toHaveBeenCalled();
    expect(getControlPlaneAuthStatusMock).not.toHaveBeenCalled();

    // Over HTTPS the same page shows the sign-in form.
    cookieValues.clear();
    requestHeaders.current = new Headers({
      host: "koda.example.com",
      "x-forwarded-host": "koda.example.com",
      "x-forwarded-proto": "https",
    });

    const viaHttps = (await LoginPage(loginProps())) as ReactElement;
    expect(viaHttps.type).toBe(loginScreenMock);
  });
});
