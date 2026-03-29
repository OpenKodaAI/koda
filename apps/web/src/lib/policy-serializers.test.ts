import { describe, expect, it } from "vitest";
import {
  normalizeModelPolicyForCore,
  parseKnowledgePolicy,
  parseMemoryPolicy,
  parseModelPolicy,
  parseResourceAccessPolicy,
  parseToolPolicy,
  serializeKnowledgePolicy,
  serializeMemoryPolicy,
  serializeModelPolicy,
  serializeResourceAccessPolicy,
  serializeToolPolicy,
} from "@/lib/policy-serializers";

describe("policy serializers", () => {
  it("maps canonical model policy fields used by the runtime", () => {
    const parsed = parseModelPolicy(
      JSON.stringify({
        allowed_providers: ["claude", "codex"],
        default_provider: "claude",
        fallback_order: ["claude", "codex"],
        available_models_by_provider: {
          claude: ["claude-sonnet-4-6"],
          codex: ["gpt-5.4"],
        },
        default_models: {
          claude: "claude-sonnet-4-6",
          codex: "gpt-5.4",
        },
      }),
    );

    expect(parsed.allowed_providers).toEqual(["claude", "codex"]);
    expect(parsed.default_provider).toBe("claude");
    expect(parsed.default_models.codex).toBe("gpt-5.4");

    const serialized = JSON.parse(serializeModelPolicy(parsed));
    expect(serialized.allowed_providers).toEqual(["claude", "codex"]);
    expect(serialized.default_provider).toBe("claude");
    expect(serialized.default_models.codex).toBe("gpt-5.4");
  });

  it("normalizes the general model envelope to general reasoning providers only", () => {
    const normalized = normalizeModelPolicyForCore(
      parseModelPolicy(
        JSON.stringify({
          allowed_providers: ["claude", "elevenlabs"],
          default_provider: "elevenlabs",
          fallback_order: ["elevenlabs", "claude"],
        }),
      ),
      {
        providers: {
          claude: {
            title: "Anthropic",
            category: "general",
            enabled: true,
            available_models: ["claude-opus-4-6"],
          },
          elevenlabs: {
            title: "ElevenLabs",
            category: "voice",
            enabled: true,
            available_models: ["eleven_v3"],
          },
        },
        enabled_providers: ["claude", "elevenlabs"],
        default_provider: "claude",
        fallback_order: ["claude"],
      },
    );

    expect(normalized.allowed_providers).toEqual(["claude"]);
    expect(normalized.default_provider).toBe("claude");
    expect(normalized.fallback_order).toEqual(["claude"]);
    expect(normalized.available_models_by_provider).toEqual({
      claude: ["claude-opus-4-6"],
    });
  });

  it("serializes tool, memory, and knowledge policies in runtime-compatible shapes", () => {
    const toolPolicy = JSON.parse(
      serializeToolPolicy({
        allowed_tool_ids: ["web_search", "fetch_url"],
        _extra: {},
      }),
    );
    expect(toolPolicy.allowed_tool_ids).toEqual(["web_search", "fetch_url"]);

    const memoryPolicy = JSON.parse(
      serializeMemoryPolicy({
        enabled: true,
        max_recall: 8,
        recall_threshold: 0.4,
        recall_timeout: 3,
        max_context_tokens: 3000,
        recency_half_life_days: 90,
        max_extraction_items: 12,
        extraction_provider: "claude",
        extraction_model: "claude-sonnet-4-6",
        proactive_enabled: false,
        procedural_enabled: true,
        procedural_max_recall: 2,
        similarity_dedup_threshold: 0.9,
        max_per_user: 500,
        maintenance_enabled: true,
        digest_enabled: true,
        risk_posture: "balanced",
        memory_density_target: "focused",
        preferred_layers: ["episodic"],
        forbidden_layers_for_actions: ["proactive"],
        focus_domains: ["ops"],
        max_items_per_turn: 4,
        observed_pattern_requires_review: true,
        minimum_verified_successes: 3,
        _extra: {},
      }),
    );
    expect(memoryPolicy.max_recall).toBe(8);
    expect(memoryPolicy.profile.focus_domains).toEqual(["ops"]);

    const knowledgePolicy = JSON.parse(
      serializeKnowledgePolicy({
        enabled: true,
        allowed_layers: ["canonical_policy", "approved_runbook"],
        max_results: 5,
        recall_threshold: 0.35,
        recall_timeout: 2,
        context_max_tokens: 1800,
        workspace_max_files: 24,
        source_globs: ["README.md"],
        workspace_source_globs: ["docs/**/*.md"],
        max_observed_patterns: 3,
        max_source_age_days: 45,
        require_owner_provenance: true,
        require_freshness_provenance: true,
        promotion_mode: "review_queue",
        _extra: {},
      }),
    );
    expect(knowledgePolicy.allowed_layers).toEqual([
      "canonical_policy",
      "approved_runbook",
    ]);
    expect(knowledgePolicy.require_owner_provenance).toBe(true);

    expect(parseToolPolicy(JSON.stringify(toolPolicy)).allowed_tool_ids).toEqual([
      "web_search",
      "fetch_url",
    ]);
    expect(parseMemoryPolicy(JSON.stringify(memoryPolicy)).focus_domains).toEqual([
      "ops",
    ]);
    expect(
      parseKnowledgePolicy(JSON.stringify(knowledgePolicy)).allowed_layers,
    ).toEqual(["canonical_policy", "approved_runbook"]);
  });

  it("serializes resource access policy for explicit grants", () => {
    const serialized = JSON.parse(
      serializeResourceAccessPolicy({
        allowed_global_secret_keys: ["OPENAI_API_KEY"],
        allowed_shared_env_keys: ["TEAM_NAME"],
        local_env: { BOT_CONTEXT_LABEL: "sales" },
        _extra: {},
      }),
    );

    expect(serialized.allowed_global_secret_keys).toEqual(["OPENAI_API_KEY"]);
    expect(serialized.allowed_shared_env_keys).toEqual(["TEAM_NAME"]);
    expect(serialized.local_env).toEqual({ BOT_CONTEXT_LABEL: "sales" });

    expect(parseResourceAccessPolicy(JSON.stringify(serialized))).toMatchObject({
      allowed_global_secret_keys: ["OPENAI_API_KEY"],
      allowed_shared_env_keys: ["TEAM_NAME"],
      local_env: { BOT_CONTEXT_LABEL: "sales" },
    });
  });
});
