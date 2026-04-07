import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const redirectMock = vi.fn();
const notFoundMock = vi.fn();
const resolveControlPlaneDashboardAccessMock = vi.fn();
const getControlPlaneBotMock = vi.fn();
const getControlPlaneSystemSettingsMock = vi.fn();
const getControlPlaneCoreToolsMock = vi.fn();
const getControlPlaneCoreProvidersMock = vi.fn();
const getControlPlaneCorePoliciesMock = vi.fn();
const getControlPlaneCoreCapabilitiesMock = vi.fn();
const getControlPlaneCoreIntegrationsMock = vi.fn();
const getControlPlaneWorkspacesMock = vi.fn();
const getControlPlaneExecutionPolicyMock = vi.fn();
const getControlPlaneCompiledPromptMock = vi.fn();

class MockControlPlaneRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

vi.mock("next/navigation", () => ({
  redirect: redirectMock,
  notFound: notFoundMock,
}));

vi.mock("@/components/control-plane/control-plane-unavailable", () => ({
  ControlPlaneUnavailable: () => <div>control-plane-unavailable</div>,
}));

vi.mock("@/components/control-plane/editor/bot-editor-shell", () => ({
  BotEditorShell: () => <div>bot-editor-shell</div>,
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
  getControlPlaneBot: getControlPlaneBotMock,
  getControlPlaneExecutionPolicy: getControlPlaneExecutionPolicyMock,
  getControlPlaneCompiledPrompt: getControlPlaneCompiledPromptMock,
  getControlPlaneCoreCapabilities: getControlPlaneCoreCapabilitiesMock,
  getControlPlaneCoreIntegrations: getControlPlaneCoreIntegrationsMock,
  getControlPlaneCorePolicies: getControlPlaneCorePoliciesMock,
  getControlPlaneCoreProviders: getControlPlaneCoreProvidersMock,
  getControlPlaneSystemSettings: getControlPlaneSystemSettingsMock,
  getControlPlaneCoreTools: getControlPlaneCoreToolsMock,
  getControlPlaneWorkspaces: getControlPlaneWorkspacesMock,
}));

describe("control-plane bot page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getControlPlaneSystemSettingsMock.mockResolvedValue({});
    getControlPlaneCoreToolsMock.mockResolvedValue([]);
    getControlPlaneCoreProvidersMock.mockResolvedValue([]);
    getControlPlaneCorePoliciesMock.mockResolvedValue([]);
    getControlPlaneCoreCapabilitiesMock.mockResolvedValue([]);
    getControlPlaneCoreIntegrationsMock.mockResolvedValue([]);
    getControlPlaneWorkspacesMock.mockResolvedValue([]);
    getControlPlaneExecutionPolicyMock.mockResolvedValue(null);
    getControlPlaneCompiledPromptMock.mockResolvedValue(null);
  });

  it("redirects private bot routes to onboarding when setup is incomplete", async () => {
    resolveControlPlaneDashboardAccessMock.mockResolvedValue({ status: "setup_required" });

    const pageModule = await import("./page");
    await pageModule.default({ params: Promise.resolve({ botId: "ATLAS" }) });

    expect(redirectMock).toHaveBeenCalledWith(
      "/control-plane/setup?next=%2Fcontrol-plane%2Fbots%2FATLAS",
    );
  });

  it("keeps bot 404s as notFound responses", async () => {
    resolveControlPlaneDashboardAccessMock.mockResolvedValue({ status: "ready" });
    getControlPlaneBotMock.mockRejectedValue(new MockControlPlaneRequestError("missing", 404));

    const pageModule = await import("./page");
    await pageModule.default({ params: Promise.resolve({ botId: "ATLAS" }) });

    expect(notFoundMock).toHaveBeenCalledTimes(1);
  });
});
