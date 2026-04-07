import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const redirectMock = vi.fn();
const resolveControlPlaneDashboardAccessMock = vi.fn();
const getGeneralSystemSettingsMock = vi.fn();
const getControlPlaneCoreIntegrationsMock = vi.fn();

class MockControlPlaneRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

vi.mock("next/navigation", () => ({
  redirect: redirectMock,
}));

vi.mock("@/components/control-plane/control-plane-unavailable", () => ({
  ControlPlaneUnavailable: () => <div>control-plane-unavailable</div>,
}));

vi.mock("@/components/control-plane/system/settings-sidebar", () => ({
  SettingsSidebar: () => <div>settings-sidebar</div>,
}));

vi.mock("@/components/control-plane/system/unsaved-changes-guard", () => ({
  UnsavedChangesGuard: () => null,
}));

vi.mock("@/components/control-plane/system/settings-modal-host", () => ({
  SettingsModalHost: () => null,
}));

vi.mock("@/components/ui/toast-notification", () => ({
  ToastNotification: () => null,
}));

vi.mock("@/hooks/use-system-settings", () => ({
  SystemSettingsProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/hooks/use-toast", () => ({
  ToastProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/lib/control-plane-dashboard-access", () => ({
  buildControlPlaneSetupHref: (nextTarget?: string | null) =>
    nextTarget
      ? `/control-plane/setup?next=${encodeURIComponent(nextTarget)}`
      : "/control-plane/setup",
  resolveControlPlaneDashboardAccess: resolveControlPlaneDashboardAccessMock,
}));

vi.mock("@/lib/control-plane", () => ({
  ControlPlaneRequestError: MockControlPlaneRequestError,
  getControlPlaneCoreIntegrations: getControlPlaneCoreIntegrationsMock,
  getGeneralSystemSettings: getGeneralSystemSettingsMock,
}));

describe("system settings layout", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("redirects system routes to onboarding when setup is incomplete", async () => {
    resolveControlPlaneDashboardAccessMock.mockResolvedValue({ status: "setup_required" });

    const layoutModule = await import("./layout");
    await layoutModule.default({ children: <div>system-child</div> });

    expect(redirectMock).toHaveBeenCalledWith("/control-plane/setup?next=%2Fcontrol-plane%2Fsystem");
  });

  it("renders the system shell once auth and onboarding are ready", async () => {
    resolveControlPlaneDashboardAccessMock.mockResolvedValue({ status: "ready" });
    getGeneralSystemSettingsMock.mockResolvedValue({});
    getControlPlaneCoreIntegrationsMock.mockResolvedValue({});

    const layoutModule = await import("./layout");
    render(await layoutModule.default({ children: <div>system-child</div> }));

    expect(screen.getByText("settings-sidebar")).toBeInTheDocument();
    expect(screen.getByText("system-child")).toBeInTheDocument();
  });
});
