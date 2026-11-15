import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AgentEditorProvider } from "@/hooks/use-agent-editor";
import { ToastProvider } from "@/hooks/use-toast";
import { TabSkills } from "@/components/control-plane/editor/tabs/tab-skills";
import type {
  ControlPlaneAgent,
  ControlPlaneCoreCapabilities,
  ControlPlaneCorePolicies,
  ControlPlaneCoreProviders,
  ControlPlaneCoreTools,
  ControlPlaneSystemSettings,
  ControlPlaneWorkspaceTree,
} from "@/lib/control-plane";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

vi.mock("@/hooks/use-app-i18n", async () => {
  const { translateForLanguage } = await vi.importActual<typeof import("@/lib/i18n")>("@/lib/i18n");
  const t = (key: string, options?: Record<string, unknown>) => translateForLanguage("en-US", key, options);

  return {
    useAppI18n: () => ({
      t,
      tl: (value: string) => value,
      i18n: { t },
      language: "en-US",
      setLanguage: vi.fn(),
      options: [],
    }),
  };
});

function makeAgent(): ControlPlaneAgent {
  return {
    id: "ATLAS",
    display_name: "ATLAS",
    status: "active",
    appearance: { label: "ATLAS", color: "#6E97D9", color_rgb: "110, 151, 217" },
    storage_namespace: "atlas",
    runtime_endpoint: {
      health_port: 8080,
      health_url: "http://127.0.0.1:8080/health",
      runtime_base_url: "http://127.0.0.1:8080",
    },
    metadata: {},
    organization: { workspace_id: null, workspace_name: null, squad_id: null, squad_name: null },
    applied_version: 1,
    desired_version: 1,
    sections: {},
    documents: {},
    knowledge_assets: [],
    knowledge_candidates: [],
    templates: [],
    skills: [],
    runbooks: [],
    secrets: [],
    draft_snapshot: {},
    published_snapshot: null,
    versions: [],
    agent_spec: {},
    compiled_prompt: "compiled",
    validation: { ok: true, errors: [], warnings: [], compiled_prompt: "compiled", documents: {} },
  } as ControlPlaneAgent;
}

const core = {
  tools: { items: [], governance: {} } satisfies ControlPlaneCoreTools,
  providers: {
    providers: {},
    enabled_providers: ["claude"],
    default_provider: "claude",
    fallback_order: ["claude"],
  } satisfies ControlPlaneCoreProviders,
  policies: {} as ControlPlaneCorePolicies,
  capabilities: { providers: [] } satisfies ControlPlaneCoreCapabilities,
};

const workspaces: ControlPlaneWorkspaceTree = {
  items: [],
  virtual_buckets: { no_workspace: { id: null, label: "No workspace", agent_count: 0 } },
  total_agent_count: 0,
};

const systemSettings: ControlPlaneSystemSettings = {
  version: 1,
  general: {},
  providers: {},
  tools: {},
  integrations: {},
  memory: {},
  knowledge: {},
  runtime: {},
  scheduler: {},
  shared_variables: [],
  additional_env_vars: [],
  global_secrets: [],
};

function registryItem(packageId: string, name: string, integrityStatus: string) {
  return {
    schema_version: "skill_registry.v1",
    agent_id: "ATLAS",
    package_id: packageId,
    name,
    version: "1.0.0",
    package_hash: `${packageId}-hash`,
    installed: true,
    recommendation_status: "recommended",
    scan_summary: { decision: "allow" },
    rollback_available: false,
    run_graph_evidence: {},
    integrity: {
      status: integrityStatus,
      approved_package_hash: `${packageId}-hash`,
      current_package_hash: integrityStatus === "verified" ? `${packageId}-hash` : "changed-hash",
    },
  };
}

function stubControlPlane() {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const body = url.endsWith("/skills/registry")
      ? {
          schema_version: "skill_registry.v1",
          agent_id: "ATLAS",
          items: [registryItem("changed_pack", "Changed Pack", "modified"), registryItem("safe_pack", "Safe Pack", "verified")],
        }
      : { items: [] };
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
}

describe("TabSkills trust registry", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("shows each installed package's integrity and says when a changed package is not loaded (D-037)", async () => {
    stubControlPlane();
    render(
      <ToastProvider>
        <AgentEditorProvider agent={makeAgent()} core={core} workspaces={workspaces} systemSettings={systemSettings}>
          <TabSkills />
        </AgentEditorProvider>
      </ToastProvider>,
    );

    const changed = (await screen.findByText("changed_pack")).closest("[data-testid=\"skill-registry-item\"]");
    const safe = screen.getByText("safe_pack").closest("[data-testid=\"skill-registry-item\"]");
    expect(changed).not.toBeNull();
    expect(safe).not.toBeNull();

    const changedCard = within(changed as HTMLElement);
    expect(changedCard.getByText("integrity:")).toBeInTheDocument();
    expect(changedCard.getByText("modified")).toBeInTheDocument();
    expect(changedCard.getByRole("status")).toHaveTextContent(
      "Files changed after approval, so its tools are not loaded. Reinstall the package and review it again.",
    );

    const safeCard = within(safe as HTMLElement);
    expect(safeCard.getByText("verified")).toBeInTheDocument();
    expect(safeCard.queryByRole("status")).not.toBeInTheDocument();
  });
});
