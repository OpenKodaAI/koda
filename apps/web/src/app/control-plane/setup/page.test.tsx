import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const redirectMock = vi.fn();
const resolveControlPlaneDashboardAccessMock = vi.fn();
const sanitizeControlPlaneNextTargetMock = vi.fn();

vi.mock("next/navigation", () => ({
  redirect: redirectMock,
}));

vi.mock("@/components/control-plane/control-plane-onboarding-shell", () => ({
  ControlPlaneOnboardingShell: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="onboarding-shell">{children}</div>
  ),
}));

vi.mock("@/components/control-plane/control-plane-setup", () => ({
  ControlPlaneSetup: () => <div>control-plane-setup</div>,
}));

vi.mock("@/components/control-plane/control-plane-unavailable", () => ({
  ControlPlaneUnavailable: () => <div>control-plane-unavailable</div>,
}));

vi.mock("@/lib/control-plane-dashboard-access", () => ({
  sanitizeControlPlaneNextTarget: sanitizeControlPlaneNextTargetMock,
  resolveControlPlaneDashboardAccess: resolveControlPlaneDashboardAccessMock,
}));

describe("control-plane setup page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sanitizeControlPlaneNextTargetMock.mockReturnValue(null);
  });

  it("renders the dedicated onboarding shell when setup is still required", async () => {
    resolveControlPlaneDashboardAccessMock.mockResolvedValue({
      status: "setup_required",
      authStatus: {},
      onboardingStatus: {},
    });

    const pageModule = await import("./page");
    render(await pageModule.default({ searchParams: Promise.resolve({}) }));

    expect(screen.getByTestId("onboarding-shell")).toBeInTheDocument();
    expect(screen.getByText("control-plane-setup")).toBeInTheDocument();
  });

  it("redirects ready sessions to the requested control-plane destination", async () => {
    sanitizeControlPlaneNextTargetMock.mockReturnValue("/control-plane/bots/ATLAS");
    resolveControlPlaneDashboardAccessMock.mockResolvedValue({ status: "ready" });

    const pageModule = await import("./page");
    await pageModule.default({
      searchParams: Promise.resolve({ next: "/control-plane/bots/ATLAS" }),
    });

    expect(redirectMock).toHaveBeenCalledWith("/control-plane/bots/ATLAS");
  });

  it("falls back to /control-plane when the next target is invalid", async () => {
    resolveControlPlaneDashboardAccessMock.mockResolvedValue({ status: "ready" });

    const pageModule = await import("./page");
    await pageModule.default({
      searchParams: Promise.resolve({ next: "https://example.com" }),
    });

    expect(redirectMock).toHaveBeenCalledWith("/control-plane");
  });
});
