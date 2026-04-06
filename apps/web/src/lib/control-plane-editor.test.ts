import { describe, expect, it } from "vitest";
import { setCurrentLanguage } from "@/lib/i18n";
import {
  buildAgentSpecPayload,
  buildBotMetadataPayload,
  parseHealthPort,
  parseJsonArray,
  parseJsonObject,
} from "@/lib/control-plane-editor";

setCurrentLanguage("pt-BR");

describe("control-plane-editor helpers", () => {
  it("preserves advanced appearance/runtime keys while applying visible fields", () => {
    const payload = buildBotMetadataPayload({
      displayName: "UI QA Bot",
      status: "paused",
      storageNamespace: "ui_qa_bot",
      workspaceId: "produto",
      squadId: "produto_platform",
      color: "#123456",
      colorRgb: "18, 52, 86",
      healthPort: "8099",
      healthUrl: "http://127.0.0.1:8099/health",
      runtimeBaseUrl: "http://127.0.0.1:8099",
      appearanceJson: JSON.stringify({
        label: "Anterior",
        color: "#ffffff",
        badge: "qa",
      }),
      runtimeEndpointJson: JSON.stringify({
        health_port: 8080,
        headers: { Authorization: "Bearer local" },
      }),
      metadataJson: JSON.stringify({
        owner: "ops",
      }),
    });

    expect(payload.appearance).toEqual({
      label: "UI QA Bot",
      color: "#123456",
      color_rgb: "18, 52, 86",
      badge: "qa",
    });
    expect(payload.runtime_endpoint).toEqual({
      health_port: 8099,
      health_url: "http://127.0.0.1:8099/health",
      runtime_base_url: "http://127.0.0.1:8099",
      headers: { Authorization: "Bearer local" },
    });
    expect(payload.metadata).toEqual({ owner: "ops" });
    expect(payload.organization).toEqual({
      workspace_id: "produto",
      squad_id: "produto_platform",
    });
  });

  it("rejects invalid health ports", () => {
    expect(() => parseHealthPort("0")).toThrow(/entre 1 e 65535/i);
    expect(() => parseHealthPort("abc")).toThrow(/entre 1 e 65535/i);
  });

  it("rejects non-object JSON payloads", () => {
    expect(() => parseJsonObject("Metadata JSON", "[]")).toThrow(
      /objeto json/i,
    );
  });

  it("rejects non-object items inside JSON arrays", () => {
    expect(() => parseJsonArray("Knowledge Assets", '[{"id":1}, "oops"]')).toThrow(
      /cada item precisa ser um objeto json/i,
    );
  });

  it("builds a typed agent-spec payload from JSON editors", () => {
    const payload = buildAgentSpecPayload({
      missionProfileJson: JSON.stringify({ mission: "Resolver tickets" }),
      interactionStyleJson: JSON.stringify({ tone: "calmo" }),
      operatingInstructionsJson: JSON.stringify({ default_workflow: ["ler", "agir"] }),
      hardRulesJson: JSON.stringify({ non_negotiables: ["nao inventar"] }),
      responsePolicyJson: JSON.stringify({ language: "pt-BR" }),
      modelPolicyJson: JSON.stringify({ allowed_providers: ["claude"] }),
      toolPolicyJson: JSON.stringify({ allowed_tool_ids: ["web_search", "fetch_url"] }),
      memoryPolicyJson: JSON.stringify({ profile: { max_items_per_turn: 4 } }),
      knowledgePolicyJson: JSON.stringify({ retrieval_mode: "grounded" }),
      autonomyPolicyJson: JSON.stringify({ default_approval_mode: "guarded" }),
      executionPolicyJson: JSON.stringify({
        version: 1,
        rules: [
          {
            name: "allow-read",
            priority: 10,
            match: { tool_id: "web_search" },
            decision: "allow",
          },
        ],
      }),
      resourceAccessPolicyJson: JSON.stringify({ allowed_global_secret_keys: ["OPENAI_API_KEY"] }),
      voicePolicyJson: JSON.stringify({ mode: "tts" }),
      imageAnalysisPolicyJson: JSON.stringify({ fallback_behavior: "describe" }),
      memoryExtractionSchemaJson: JSON.stringify({ template: "{query} {response} {max_items}" }),
      skillPolicyJson: JSON.stringify({ enabled: true }),
      customSkillsJson: JSON.stringify([{ id: "s1", name: "test-skill" }]),
    });

    expect(payload.mission_profile).toEqual({ mission: "Resolver tickets" });
    expect(payload.tool_policy).toEqual({
      allowed_tool_ids: ["web_search", "fetch_url"],
    });
    expect(payload.autonomy_policy).toEqual({
      default_approval_mode: "guarded",
    });
    expect(payload.execution_policy).toEqual({
      version: 1,
      rules: [
        {
          name: "allow-read",
          priority: 10,
          match: { tool_id: "web_search" },
          decision: "allow",
        },
      ],
    });
    expect(payload.resource_access_policy).toEqual({
      allowed_global_secret_keys: ["OPENAI_API_KEY"],
    });
    expect(payload.memory_extraction_schema).toEqual({
      template: "{query} {response} {max_items}",
    });
  });

  it("omits execution policy when the editor leaves it unset", () => {
    const payload = buildAgentSpecPayload({
      missionProfileJson: "{}",
      interactionStyleJson: "{}",
      operatingInstructionsJson: "{}",
      hardRulesJson: "{}",
      responsePolicyJson: "{}",
      modelPolicyJson: "{}",
      toolPolicyJson: "{}",
      memoryPolicyJson: "{}",
      knowledgePolicyJson: "{}",
      autonomyPolicyJson: "{}",
      resourceAccessPolicyJson: "{}",
      voicePolicyJson: "{}",
      imageAnalysisPolicyJson: "{}",
      memoryExtractionSchemaJson: "{}",
    });

    expect(payload).not.toHaveProperty("execution_policy");
  });
});
