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

  it("uses cached catalog reads for bot listings", async () => {
    const { getControlPlaneBots } = await import("@/lib/control-plane");

    await getControlPlaneBots();

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

  it("uses detail caching for bot configuration pages", async () => {
    const { getControlPlaneBot } = await import("@/lib/control-plane");

    await getControlPlaneBot("ATLAS");

    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.any(URL),
      expect.objectContaining({
        cache: "force-cache",
        next: expect.objectContaining({
          revalidate: 5,
          tags: expect.arrayContaining(["control-plane:bot:ATLAS"]),
        }),
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
          tags: expect.arrayContaining(["control-plane:bot:ATLAS"]),
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
              integration_credentials: {
                jira: {
                  title: "Jira",
                  description: "credentials",
                  fields: [
                    {
                      key: "api_key",
                      label: "API key",
                      input_type: "password",
                      storage: "secret",
                      required: true,
                      value: "jira-secret",
                      preview: "jira-...",
                      value_present: true,
                    },
                  ],
                },
              },
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
    expect(payload.values.integration_credentials.jira.fields[0].value).toBe("");
    expect(payload.values.integration_credentials.jira.fields[0].preview).toBe("");
    expect(payload.values.provider_connections.openai.api_key_preview).toBe("");
  });

  it("removes secret previews and raw values from bot detail payloads", async () => {
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
                scope: "bot",
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

    const { getControlPlaneBot } = await import("@/lib/control-plane");
    const payload = await getControlPlaneBot("ATLAS");

    expect(payload.secrets[0]).toEqual(
      expect.objectContaining({
        preview: "",
        value: "",
      }),
    );
  });
});
