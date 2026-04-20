import { describe, it, expect } from "vitest";
import {
  groupErrorsBySection,
  sectionForField,
  validatePayloadClientSide,
} from "./system-settings-schema";

describe("validatePayloadClientSide", () => {
  it("accepts an empty payload", () => {
    expect(validatePayloadClientSide({})).toEqual([]);
  });

  it("accepts a payload with nullable budget fields", () => {
    expect(
      validatePayloadClientSide({
        models: { max_budget_usd: null, max_total_budget_usd: null },
      }),
    ).toEqual([]);
  });

  it("rejects negative task budget", () => {
    const errors = validatePayloadClientSide({ models: { max_budget_usd: -1 } });
    expect(errors.some((e) => e.code === "must_be_positive")).toBe(true);
  });

  it("rejects total budget below task budget", () => {
    const errors = validatePayloadClientSide({
      models: { max_budget_usd: 10, max_total_budget_usd: 5 },
    });
    expect(errors.some((e) => e.code === "must_gte_max_budget")).toBe(true);
  });

  it("rejects default_provider not in providers_enabled", () => {
    const errors = validatePayloadClientSide({
      models: { providers_enabled: ["claude"], default_provider: "gemini" },
    });
    expect(errors.some((e) => e.code === "must_be_enabled")).toBe(true);
  });

  it("rejects functional_default pointing to disabled provider", () => {
    const errors = validatePayloadClientSide({
      models: {
        providers_enabled: ["claude"],
        functional_defaults: { general: { provider_id: "gemini", model_id: "g" } },
      },
    });
    expect(errors.some((e) => e.code === "must_be_enabled")).toBe(true);
  });

  it("rejects variable with lowercase key", () => {
    const errors = validatePayloadClientSide({
      variables: [{ key: "lowercase", type: "text", scope: "system_only" }],
    });
    expect(errors.some((e) => e.code === "invalid_format")).toBe(true);
  });

  it("rejects variable with unknown scope", () => {
    const errors = validatePayloadClientSide({
      variables: [{ key: "OK", type: "text", scope: "mystery" }],
    });
    expect(errors.some((e) => e.code === "invalid_enum")).toBe(true);
  });

  it("rejects invalid autonomy tier", () => {
    const errors = validatePayloadClientSide({
      memory_and_knowledge: { autonomy_policy: { default_autonomy_tier: "t9" } },
    });
    expect(errors.some((e) => e.code === "invalid_enum")).toBe(true);
  });

  it("rejects zero rate limit", () => {
    const errors = validatePayloadClientSide({
      account: { rate_limit_per_minute: 0 },
    });
    expect(errors.some((e) => e.code === "min_value")).toBe(true);
  });
});

describe("sectionForField", () => {
  it.each([
    ["account.rate_limit_per_minute", "general"],
    ["models.max_budget_usd", "models"],
    ["models.functional_defaults.general.provider_id", "models"],
    ["resources.global_tools", "integrations"],
    ["memory_and_knowledge.autonomy_policy.default_autonomy_tier", "intelligence"],
    ["variables.0.key", "variables"],
    ["variables", "variables"],
    ["unknown.field", "general"],
  ])("maps %s to %s", (field, expected) => {
    expect(sectionForField(field)).toBe(expected);
  });
});

describe("groupErrorsBySection", () => {
  it("buckets errors by section", () => {
    const grouped = groupErrorsBySection([
      { field: "account.rate_limit_per_minute", code: "min_value", message: "x" },
      { field: "models.max_budget_usd", code: "must_be_positive", message: "y" },
      { field: "variables.0.key", code: "required", message: "z" },
    ]);
    expect(grouped.general).toHaveLength(1);
    expect(grouped.models).toHaveLength(1);
    expect(grouped.variables).toHaveLength(1);
    expect(grouped.integrations).toHaveLength(0);
    expect(grouped.intelligence).toHaveLength(0);
  });
});
