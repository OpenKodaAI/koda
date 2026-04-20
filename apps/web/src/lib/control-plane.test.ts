import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/web-operator-session", () => ({
  getWebOperatorTokenFromCookie: vi.fn(async () => "operator-token"),
}));

describe("control-plane fetch tiers", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ items: [], bot_id: "ATLAS" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses cached catalog reads for agent listings", async () => {
    const { getControlPlaneAgents } = await import("@/lib/control-plane");

    await getControlPlaneAgents();

    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.any(URL),
      expect.objectContaining({
        cache: "force-cache",
        next: expect.objectContaining({
          revalidate: 15,
          tags: expect.arrayContaining(["control-plane:catalog"]),
        }),
      }),
    );
  });

  it("uses cached catalog reads for workspace organization trees", async () => {
    const { getControlPlaneWorkspaces } = await import("@/lib/control-plane");

    await getControlPlaneWorkspaces();

    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.any(URL),
      expect.objectContaining({
        cache: "force-cache",
        next: expect.objectContaining({
          revalidate: 15,
          tags: expect.arrayContaining(["control-plane:workspaces"]),
        }),
      }),
    );
  });

  it("uses live fetching for agent configuration pages", async () => {
    const { getControlPlaneAgent } = await import("@/lib/control-plane");

    await getControlPlaneAgent("ATLAS");

    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.any(URL),
      expect.objectContaining({
        cache: "no-store",
      }),
    );
  });

  it("uses detail caching for compiled prompt previews", async () => {
    const { getControlPlaneCompiledPrompt } = await import("@/lib/control-plane");

    await getControlPlaneCompiledPrompt("ATLAS");

    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.any(URL),
      expect.objectContaining({
        cache: "force-cache",
        next: expect.objectContaining({
          revalidate: 5,
          tags: expect.arrayContaining(["control-plane:agent:ATLAS"]),
        }),
      }),
    );
  });

  it("keeps runtime access requests live", async () => {
    const { getControlPlaneRuntimeAccess } = await import("@/lib/control-plane");

    await getControlPlaneRuntimeAccess("ATLAS");

    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.any(URL),
      expect.objectContaining({
        cache: "no-store",
      }),
    );
  });

  it("strips runtime tokens from runtime access payloads before returning them", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            bot_id: "ATLAS",
            health_url: "http://127.0.0.1:8080/health",
            runtime_base_url: "http://127.0.0.1:8080",
            runtime_token: null,
            runtime_request_token: "scoped-runtime-request-token",
            access_scope_token: "signed-scope-token",
            runtime_token_present: true,
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );

    const { getControlPlaneRuntimeAccess } = await import("@/lib/control-plane");
    const payload = await getControlPlaneRuntimeAccess("ATLAS");

    expect(payload.runtime_token).toBeNull();
    expect(payload.runtime_request_token).toBeNull();
    expect(payload.access_scope_token).toBeNull();
    expect(payload.runtime_token_present).toBe(true);
  });

  it("preserves runtime access tokens for server-only callers", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            bot_id: "ATLAS",
            health_url: "http://127.0.0.1:8080/health",
            runtime_base_url: "http://127.0.0.1:8080",
            runtime_token: null,
            runtime_request_token: "scoped-runtime-request-token",
            access_scope_token: "signed-scope-token",
            runtime_token_present: true,
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );

    const { getServerControlPlaneRuntimeAccess } = await import("@/lib/control-plane");
    const payload = await getServerControlPlaneRuntimeAccess("ATLAS");

    expect(payload.runtime_token).toBeNull();
    expect(payload.runtime_request_token).toBe("scoped-runtime-request-token");
    expect(payload.access_scope_token).toBe("signed-scope-token");
  });

  it("removes secret previews and values from general system settings payloads", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            version: 1,
            values: {
              account: {},
              models: { functional_defaults: {} },
              resources: { global_tools: [], integrations: {} },
              memory_and_knowledge: {
                memory_policy: {},
                knowledge_policy: {},
                autonomy_policy: {},
              },
              variables: [
                {
                  key: "OPENAI_API_KEY",
                  type: "secret",
                  scope: "system_only",
                  description: "secret",
                  value: "sk-live-secret",
                  preview: "sk-live...",
                  value_present: true,
                },
              ],
              provider_connections: {
                openai: {
                  provider_id: "openai",
                  title: "OpenAI",
                  auth_mode: "api_key",
                  configured: true,
                  verified: true,
                  account_label: "",
                  plan_label: "",
                  last_verified_at: "",
                  last_error: "",
                  project_id: "",
                  command_present: true,
                  supports_api_key: true,
                  supports_subscription_login: false,
                  supported_auth_modes: ["api_key"],
                  requires_project_id: false,
                  api_key_present: true,
                  api_key_preview: "sk-live...",
                  connection_status: "verified",
                },
              },
            },
            source_badges: {},
            catalogs: {
              providers: [],
              model_functions: [],
              functional_model_catalog: {},
              global_tools: [],
              usage_profiles: [],
              memory_profiles: [],
              knowledge_profiles: [],
              provenance_policies: [],
              knowledge_layers: [],
              approval_modes: [],
              autonomy_tiers: [],
            },
            review: { warnings: [], hidden_sections: [] },
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );

    const { getGeneralSystemSettings } = await import("@/lib/control-plane");
    const payload = await getGeneralSystemSettings();

    expect(payload.values.variables[0].value).toBe("");
    expect(payload.values.variables[0].preview).toBe("");
    expect(payload.values.provider_connections.openai.api_key_preview).toBe("");
  });

  it("removes secret previews and raw values from agent detail payloads", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            id: "ATLAS",
            display_name: "ATLAS",
            status: "active",
            appearance: {},
            storage_namespace: "masp",
            runtime_endpoint: {},
            metadata: {},
            organization: {},
            sections: {},
            documents: {},
            knowledge_assets: [],
            templates: [],
            skills: [],
            secrets: [
              {
                scope: "agent",
                secret_key: "OPENAI_API_KEY",
                preview: "sk-live...",
                value: "sk-live-secret",
              },
            ],
            draft_snapshot: {},
            published_snapshot: null,
            versions: [],
            agent_spec: {},
            compiled_prompt: "",
            validation: { ok: true, errors: [], warnings: [], compiled_prompt: "", documents: {} },
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );

    const { getControlPlaneAgent } = await import("@/lib/control-plane");
    const payload = await getControlPlaneAgent("ATLAS");

    expect(payload.secrets[0]).toEqual(
      expect.objectContaining({
        preview: "",
        value: "",
      }),
    );
  });

  it("strips decrypted value from include_value secret responses proxied to browser", async () => {
    // When the backend returns a secret with include_value=true (decrypted value present),
    // the sanitizer must blank the value before it reaches the browser through the proxy.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            id: 42,
            scope: "agent",
            secret_key: "DISCORD_BOT_TOKEN",
            preview: "Agent****",
            value: "real-discord-token-should-be-stripped",
            updated_at: "2026-04-04T00:00:00Z",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );

    const { controlPlaneFetchJson } = await import("@/lib/control-plane");
    const payload = await controlPlaneFetchJson<Record<string, unknown>>(
      "/api/control-plane/agents/agent-1/secrets/DISCORD_BOT_TOKEN",
    );

    expect(payload.secret_key).toBe("DISCORD_BOT_TOKEN");
    expect(payload.value).toBe("");
    expect(payload.preview).toBe("");
  });

  it("derives core integrations from the canonical catalog and defaults endpoints", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.includes("/api/control-plane/connections/catalog")) {
        return new Response(
          JSON.stringify({
            items: [
              {
                connection_key: "core:browser",
                kind: "core",
                integration_key: "browser",
                display_name: "Browser",
                description: "Governed browser automation",
                category: "productivity",
                transport_kind: "browser",
                auth_capabilities: { modes: ["none"] },
                auth_strategy_default: "none",
                enabled: true,
              },
            ],
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      if (url.includes("/api/control-plane/connections/defaults")) {
        return new Response(
          JSON.stringify({
            items: [
              {
                connection_key: "core:browser",
                kind: "core",
                integration_key: "browser",
                status: "verified",
                auth_strategy: "none",
                auth_method: "none",
                source_origin: "system_default",
                account_label: "runtime managed",
                provider_account_id: null,
                expires_at: null,
                last_verified_at: "2026-03-30T10:00:00Z",
                last_error: "",
                tool_count: 3,
                connected: true,
                enabled: true,
                metadata: {
                  checked_via: "browser_runtime",
                  health_probe: "browser_manager",
                  supports_persistence: true,
                  session_scope: "task",
                },
                fields: [],
              },
            ],
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      throw new Error(`Unhandled fetch: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    const { getControlPlaneCoreIntegrations } = await import("@/lib/control-plane");
    const payload = await getControlPlaneCoreIntegrations();

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      expect.any(URL),
      expect.objectContaining({
        cache: "force-cache",
        next: expect.objectContaining({
          revalidate: 15,
          tags: expect.arrayContaining(["control-plane:core"]),
        }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.any(URL),
      expect.objectContaining({
        cache: "force-cache",
        next: expect.objectContaining({
          revalidate: 5,
          tags: expect.arrayContaining(["control-plane:core"]),
        }),
      }),
    );
    expect(payload.items[0].connection?.integration_id).toBe("browser");
    expect(payload.items[0].connection?.checked_via).toBe("browser_runtime");
    expect(payload.items[0].connection_status).toBe("verified");
    expect(payload.governance?.source_of_truth).toBe("connections_catalog_and_defaults");
  });
});
