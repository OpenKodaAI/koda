import { describe, it, expect } from "vitest";
import {
  findFieldError,
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

  it("accepts valid scheduler block", () => {
    const errors = validatePayloadClientSide({
      scheduler: {
        scheduler_enabled: true,
        scheduler_poll_interval_seconds: 5,
        runbook_governance_enabled: true,
        runbook_governance_hour: 4,
        runbook_revalidation_min_success_rate: 0.9,
      },
    });
    expect(errors).toEqual([]);
  });

  it("rejects scheduler_poll_interval_seconds below 1", () => {
    const errors = validatePayloadClientSide({
      scheduler: { scheduler_poll_interval_seconds: 0 },
    });
    expect(errors.some((e) => e.code === "min_value")).toBe(true);
  });

  it("rejects runbook_governance_hour out of 0-23 range", () => {
    const errors = validatePayloadClientSide({
      scheduler: { runbook_governance_hour: 30 },
    });
    expect(errors.some((e) => e.code === "out_of_range")).toBe(true);
  });

  it("rejects runbook_revalidation_min_success_rate outside 0-1", () => {
    const errors = validatePayloadClientSide({
      scheduler: { runbook_revalidation_min_success_rate: 1.5 },
    });
    expect(errors.some((e) => e.code === "out_of_range")).toBe(true);
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

describe("findFieldError", () => {
  const errors = [
    { field: "models.max_budget_usd", code: "must_be_positive", message: "a" },
    { field: "variables.2.key", code: "invalid_format", message: "b" },
    { field: "variables.2.scope", code: "invalid_enum", message: "c" },
    {
      field: "models.functional_defaults.audio.provider_id",
      code: "must_be_enabled",
      message: "d",
    },
  ];

  it("finds exact match", () => {
    expect(findFieldError(errors, "models.max_budget_usd")?.message).toBe("a");
  });

  it("finds first prefix match when exact not present", () => {
    expect(findFieldError(errors, "variables.2")?.message).toBe("b");
  });

  it("returns undefined when no error matches", () => {
    expect(findFieldError(errors, "models.max_total_budget_usd")).toBeUndefined();
  });

  it("handles empty or nullish error list", () => {
    expect(findFieldError([], "models.max_budget_usd")).toBeUndefined();
    expect(findFieldError(undefined, "x")).toBeUndefined();
    expect(findFieldError(null, "x")).toBeUndefined();
  });

  it("does not pick partial-segment matches", () => {
    // "models.max" must NOT match "models.max_budget_usd" — we only match on
    // full segment boundaries via the trailing dot.
    expect(findFieldError(errors, "models.max")).toBeUndefined();
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
