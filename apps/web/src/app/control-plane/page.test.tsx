import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const redirectMock = vi.fn();
const resolveControlPlaneDashboardAccessMock = vi.fn();
const getControlPlaneBotsMock = vi.fn();
const getControlPlaneCoreProvidersMock = vi.fn();
const getControlPlaneWorkspacesMock = vi.fn();
const getGeneralSystemSettingsMock = vi.fn();

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

vi.mock("@/components/control-plane/catalog/catalog-layout", () => ({
  CatalogLayout: ({ bots }: { bots: Array<{ id: string }> }) => (
    <div>catalog-layout:{bots.length}</div>
  ),
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
  getControlPlaneBots: getControlPlaneBotsMock,
  getControlPlaneCoreProviders: getControlPlaneCoreProvidersMock,
  getControlPlaneWorkspaces: getControlPlaneWorkspacesMock,
  getGeneralSystemSettings: getGeneralSystemSettingsMock,
}));

describe("control-plane page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("redirects to the dedicated onboarding route when setup is incomplete", async () => {
    resolveControlPlaneDashboardAccessMock.mockResolvedValue({ status: "setup_required" });

    const pageModule = await import("./page");
    await pageModule.default();

    expect(redirectMock).toHaveBeenCalledWith("/control-plane/setup");
  });

  it("renders the catalog when auth and onboarding are ready", async () => {
    resolveControlPlaneDashboardAccessMock.mockResolvedValue({ status: "ready" });
    getControlPlaneBotsMock.mockResolvedValue([{ id: "ATLAS" }]);
    getControlPlaneCoreProvidersMock.mockResolvedValue([]);
    getControlPlaneWorkspacesMock.mockResolvedValue({ items: [], virtual_buckets: {}, total_bot_count: 0 });
    getGeneralSystemSettingsMock.mockResolvedValue(null);

    const pageModule = await import("./page");
    render(await pageModule.default());

    expect(screen.getByText("catalog-layout:1")).toBeInTheDocument();
  });

  it("shows the unavailable screen when the public status probe fails", async () => {
    resolveControlPlaneDashboardAccessMock.mockResolvedValue({
      status: "unavailable",
      error: new Error("offline"),
    });

    const pageModule = await import("./page");
    render(await pageModule.default());

    expect(screen.getByText("control-plane-unavailable")).toBeInTheDocument();
  });
});
