import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const getControlPlaneAuthStatusMock = vi.fn();
const getControlPlaneOnboardingStatusMock = vi.fn();

vi.mock("@/lib/control-plane", () => ({
  getControlPlaneAuthStatus: getControlPlaneAuthStatusMock,
  getControlPlaneOnboardingStatus: getControlPlaneOnboardingStatusMock,
}));

describe("control-plane dashboard access", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("accepts only internal control-plane next targets", async () => {
    const { sanitizeControlPlaneNextTarget } = await import("./control-plane-dashboard-access");

    expect(sanitizeControlPlaneNextTarget("/control-plane/bots/ATLAS?tab=tools")).toBe(
      "/control-plane/bots/ATLAS?tab=tools",
    );
    expect(sanitizeControlPlaneNextTarget("/control-plane")).toBe("/control-plane");
    expect(sanitizeControlPlaneNextTarget("/control-plane/setup")).toBeNull();
    expect(sanitizeControlPlaneNextTarget("/control-planeevil")).toBeNull();
    expect(sanitizeControlPlaneNextTarget("https://example.com/control-plane")).toBeNull();
    expect(sanitizeControlPlaneNextTarget("//example.com/control-plane")).toBeNull();
  });

  it("returns ready when auth and onboarding are complete", async () => {
    getControlPlaneAuthStatusMock.mockResolvedValue({
      authenticated: true,
      has_owner: true,
      bootstrap_required: false,
      auth_mode: "local_account",
      session_required: true,
      recovery_available: true,
    });
    getControlPlaneOnboardingStatusMock.mockResolvedValue({
      steps: {
        onboarding_complete: true,
      },
    });

    const { resolveControlPlaneDashboardAccess } = await import("./control-plane-dashboard-access");
    const result = await resolveControlPlaneDashboardAccess();

    expect(result.status).toBe("ready");
  });

  it("returns setup_required when the dashboard still needs owner auth or bootstrap", async () => {
    getControlPlaneAuthStatusMock.mockResolvedValue({
      authenticated: false,
      has_owner: true,
      bootstrap_required: false,
      auth_mode: "local_account",
      session_required: true,
      recovery_available: true,
    });
    getControlPlaneOnboardingStatusMock.mockResolvedValue({
      steps: {
        onboarding_complete: true,
      },
    });

    const { resolveControlPlaneDashboardAccess } = await import("./control-plane-dashboard-access");
    const result = await resolveControlPlaneDashboardAccess();

    expect(result.status).toBe("setup_required");
  });

  it("returns unavailable when the public status probe fails", async () => {
    getControlPlaneAuthStatusMock.mockRejectedValue(new Error("offline"));

    const { resolveControlPlaneDashboardAccess } = await import("./control-plane-dashboard-access");
    const result = await resolveControlPlaneDashboardAccess();

    expect(result.status).toBe("unavailable");
  });
});
