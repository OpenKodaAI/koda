import { describe, expect, it } from "vitest";
import { setCurrentLanguage } from "@/lib/i18n";
import {
  normalizeFallbackOrder,
  STEP_TO_SECTION,
  sanitizeVariableDraft,
  sourceBadgeLabel,
  upsertVariable,
} from "@/lib/system-settings-model";

setCurrentLanguage("pt-BR");

describe("system settings model helpers", () => {
  it("normalizes fallback order around enabled providers and default provider", () => {
    expect(normalizeFallbackOrder(["claude", "codex"], ["codex"], "claude")).toEqual([
      "claude",
      "codex",
    ]);
    expect(normalizeFallbackOrder(["codex"], ["claude", "codex"], "claude")).toEqual(["codex"]);
  });

  it("sanitizes variable drafts into env-style keys", () => {
    expect(
      sanitizeVariableDraft({
        key: " jira api token ",
        type: "secret",
        scope: "bot_grant",
      }),
    ).toMatchObject({
      key: "JIRA_API_TOKEN",
      type: "secret",
      scope: "bot_grant",
    });
  });

  it("upserts variables by key", () => {
    const next = upsertVariable(
      [
        {
          key: "TEAM_NAME",
          type: "text",
          scope: "system_only",
          description: "",
          value: "platform",
          preview: "platform",
          value_present: true,
        },
      ],
      {
        key: "TEAM_NAME",
        type: "text",
        scope: "bot_grant",
        description: "queue",
        value: "ops",
        preview: "ops",
        value_present: true,
      },
    );
    expect(next).toEqual([
      {
        key: "TEAM_NAME",
        type: "text",
        scope: "bot_grant",
        description: "queue",
        value: "ops",
        preview: "ops",
        value_present: true,
        clear: false,
      },
    ]);
  });

  it("renders human-readable source labels", () => {
    expect(sourceBadgeLabel("custom")).toBe("Personalizado");
    expect(sourceBadgeLabel("env")).toBe("Vindo do .env");
    expect(sourceBadgeLabel("system_default")).toBe("Padrão do sistema");
  });

  it("maps legacy onboarding step ids to the current section ids", () => {
    expect(STEP_TO_SECTION).toMatchObject({
      account: "general",
      models: "models",
      integrations: "integrations",
      memory: "intelligence",
      variables: "intelligence",
      review: "general",
    });
  });
});
