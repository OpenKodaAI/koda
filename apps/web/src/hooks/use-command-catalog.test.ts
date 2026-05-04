import { describe, expect, it } from "vitest";
import { skillsFromAgentSpec } from "@/hooks/use-command-catalog";

describe("skillsFromAgentSpec", () => {
  it("returns only enabled custom skills from the current agent spec", () => {
    const skills = skillsFromAgentSpec({
      custom_skills: [
        {
          id: "deploy-review",
          name: "Deploy Review",
          category: "operations",
          instruction: "Review deploy plans",
          content: "<when_to_use>Use before production deploys.</when_to_use>",
        },
        {
          id: "disabled",
          name: "Disabled",
          enabled: false,
          content: "hidden",
        },
      ],
      skill_policy: { enabled: true },
    });

    expect(skills).toEqual([
      {
        id: "deploy-review",
        title: "Deploy Review",
        description: "Use before production deploys.",
        category: "operations",
      },
    ]);
  });

  it("respects skill_policy enabled, allow-list, and block-list", () => {
    expect(
      skillsFromAgentSpec({
        custom_skills: [{ id: "review", name: "Review", content: "body" }],
        skill_policy: { enabled: false },
      }),
    ).toEqual([]);

    expect(
      skillsFromAgentSpec({
        custom_skills: [
          { id: "review", name: "Review", content: "body" },
          { id: "security", name: "Security", content: "body" },
          { id: "legacy", name: "Legacy", content: "body" },
        ],
        skill_policy: {
          enabled_skills: ["review", "security"],
          disabled_skills: ["security"],
        },
      }),
    ).toEqual([
      {
        id: "review",
        title: "Review",
        description: undefined,
        category: "skill",
      },
    ]);
  });
});
