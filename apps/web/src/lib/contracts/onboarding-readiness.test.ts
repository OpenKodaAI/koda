import { describe, expect, it } from "vitest";
import "@/lib/contracts/onboarding-readiness";
import {
  onboardingFirstTaskBodySchema,
  parseOnboardingReadiness,
} from "@/lib/contracts/onboarding-readiness";
import { resolveBodySchema } from "@/lib/contracts/proxy-body-schemas";

describe("Phase 6 onboarding readiness contracts", () => {
  it("parses onboarding_readiness.v1 checks and actions", () => {
    const readiness = parseOnboardingReadiness({
      schema_version: "onboarding_readiness.v1",
      status: "warning",
      primary_agent_id: "ATLAS",
      checks: [
        {
          key: "provider",
          title: "Provider",
          status: "passed",
          summary: "A verified provider is configured.",
        },
        {
          key: "channel",
          title: "Channel",
          status: "warning",
          summary: "Telegram is connected but no sender is paired.",
          action_label: "Open gateway",
          action_href: "/control-plane",
        },
      ],
      summary: { passed: 1, warning: 1, failed: 0, pending: 0 },
      actions: [{ check: "channel", label: "Open gateway", href: "/control-plane" }],
    });

    expect(readiness.schema_version).toBe("onboarding_readiness.v1");
    expect(readiness.status).toBe("warning");
    expect(readiness.checks.find((check) => check.key === "channel")?.status).toBe("warning");
    expect(readiness.actions[0]?.label).toBe("Open gateway");
  });

  it("registers first-task proxy schema", () => {
    const schema = resolveBodySchema("POST", ["onboarding", "first-task"]);

    expect(schema).toBe(onboardingFirstTaskBodySchema);
    expect(schema?.parse({ agent_id: "ATLAS", text: "Run a smoke task." })).toEqual({
      agent_id: "ATLAS",
      text: "Run a smoke task.",
    });
  });
});
