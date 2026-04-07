import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { IntegrationDetailView } from "@/components/control-plane/system/integrations/integration-detail-view";
import { INTEGRATION_CATALOG } from "@/components/control-plane/system/integrations/integration-catalog-data";
import type { UnifiedIntegrationEntry } from "@/components/control-plane/system/integrations/integration-marketplace-data";

const useSystemSettingsMock = vi.fn();

vi.mock("@/hooks/use-app-i18n", () => ({
  useAppI18n: () => ({
    tl: (value: string) => value,
  }),
}));

vi.mock("@/hooks/use-system-settings", () => ({
  useSystemSettings: () => useSystemSettingsMock(),
}));

vi.mock("@/components/control-plane/system/integrations/integration-logos", () => ({
  renderIntegrationLogo: () => null,
}));

describe("IntegrationDetailView", () => {
  beforeEach(() => {
    useSystemSettingsMock.mockReset();
  });

  it("auto-verifies browser connections when the detail view opens and keeps the system toggle internal", async () => {
    const browserEntry = INTEGRATION_CATALOG.find((entry) => entry.key === "browser");
    expect(browserEntry).toBeTruthy();
    const unifiedBrowserEntry: UnifiedIntegrationEntry = {
      id: `core:${browserEntry!.key}`,
      key: browserEntry!.key,
      kind: "core",
      status: "connected",
      label: browserEntry!.label,
      tagline: browserEntry!.tagline,
      description: browserEntry!.description,
      category: browserEntry!.category,
      logoKey: browserEntry!.logoKey,
      gradientFrom: browserEntry!.gradientFrom,
      gradientTo: browserEntry!.gradientTo,
      promptExample: browserEntry!.promptExample,
      capabilities: browserEntry!.capabilities,
      metadata: {
        developer: browserEntry!.metadata.developer,
        type: browserEntry!.metadata.type,
        documentationUrl: browserEntry!.metadata.documentationUrl,
      },
      searchText: "",
      core: {
        entry: browserEntry!,
      },
    };

    const ensureIntegrationConnectionFresh = vi.fn().mockResolvedValue(null);

    useSystemSettingsMock.mockReturnValue({
      draft: {
        values: {
          resources: {
            integrations: {
              browser_enabled: true,
            },
          },
        },
      },
      connectionDefaults: [
        {
          connection_key: "core:browser",
          kind: "core",
          integration_key: "browser",
          status: "configured",
          auth_method: "none",
          connected: true,
          enabled: true,
          metadata: {
            checked_via: "browser_manager",
          },
          fields: [],
        },
      ],
      integrationCatalog: [
        {
          id: "browser",
          title: "Browser",
          transport: "browser",
          auth_modes: [],
          supports_persistence: true,
          actions: [],
          connection: {
            integration_id: "browser",
            title: "Browser",
            description: "",
            transport: "browser",
            auth_modes: [],
            auth_mode: "none",
            configured: true,
            verified: false,
            account_label: "",
            last_verified_at: "",
            last_error: "",
            checked_via: "",
            auth_expired: false,
            metadata: {},
            fields: [],
            supports_persistence: true,
            connection_status: "configured",
          },
        },
      ],
      integrationConnections: {
        browser: {
          integration_id: "browser",
          title: "Browser",
          description: "",
          transport: "browser",
          auth_modes: [],
          auth_mode: "none",
          configured: true,
          verified: false,
          account_label: "",
          last_verified_at: "",
          last_error: "",
          checked_via: "",
          auth_expired: false,
          metadata: {},
          fields: [],
          supports_persistence: true,
          connection_status: "configured",
        },
      },
      ensureIntegrationConnectionFresh,
      connectIntegration: vi.fn(),
      disconnectIntegrationConnection: vi.fn(),
      isIntegrationActionPending: vi.fn(() => false),
      integrationActionStatus: vi.fn(() => "idle"),
    });

    render(
      <IntegrationDetailView
        entry={unifiedBrowserEntry}
        onBack={vi.fn()}
        onConnect={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(ensureIntegrationConnectionFresh).toHaveBeenCalledWith("browser");
    });

    expect(screen.queryByRole("button", { name: "Ativar no sistema" })).not.toBeInTheDocument();
    expect(screen.getAllByText("Gerenciada internamente").length).toBeGreaterThan(0);
  });
});
