import { describe, expect, it } from "vitest";
import {
  STATIC_COMMAND_FALLBACK,
  chatCommandSchema,
  chatCommandsCatalogSchema,
  skillSearchResponseSchema,
  skillSuggestionSchema,
} from "@/lib/contracts/chat-commands";

describe("chatCommandSchema", () => {
  it("accepts an insert action", () => {
    const r = chatCommandSchema.safeParse({
      id: "macro-deploy",
      label: "/macro-deploy",
      description: "Insert deploy template.",
      action: { kind: "insert", template: "/macro-deploy " },
    });
    expect(r.success).toBe(true);
  });

  it("accepts an execute action with payload", () => {
    const r = chatCommandSchema.safeParse({
      id: "switch-agent",
      label: "/switch",
      description: "Switch agent.",
      action: { kind: "execute", type: "switch-agent", payload: { agent_id: "BOT1" } },
    });
    expect(r.success).toBe(true);
  });

  it("rejects unknown execute type", () => {
    const r = chatCommandSchema.safeParse({
      id: "x",
      label: "/x",
      description: "x",
      action: { kind: "execute", type: "explode" },
    });
    expect(r.success).toBe(false);
  });

  it("rejects ids with spaces or uppercase", () => {
    expect(
      chatCommandSchema.safeParse({
        id: "Bad ID",
        label: "/x",
        description: "x",
        action: { kind: "insert", template: "/x " },
      }).success,
    ).toBe(false);
  });
});

describe("chatCommandsCatalogSchema", () => {
  it("validates the static fallback catalog", () => {
    const r = chatCommandsCatalogSchema.safeParse({ items: STATIC_COMMAND_FALLBACK });
    expect(r.success).toBe(true);
  });

  it("rejects > 64 items", () => {
    const items = Array.from({ length: 65 }, (_, i) => ({
      id: `cmd-${i}`,
      label: `/c${i}`,
      description: "x",
      action: { kind: "insert" as const, template: `/c${i} ` },
    }));
    const r = chatCommandsCatalogSchema.safeParse({ items });
    expect(r.success).toBe(false);
  });
});

describe("skillSuggestionSchema", () => {
  it("accepts minimal record with slug + label", () => {
    const r = skillSuggestionSchema.safeParse({ slug: "python_dev", label: "Python dev" });
    expect(r.success).toBe(true);
  });

  it("rejects bad slug formats", () => {
    expect(skillSuggestionSchema.safeParse({ slug: "PythonDev", label: "x" }).success).toBe(false);
    expect(skillSuggestionSchema.safeParse({ slug: "", label: "x" }).success).toBe(false);
  });

  it("validates color format", () => {
    expect(
      skillSuggestionSchema.safeParse({ slug: "x", label: "x", color: "#abcdef" }).success,
    ).toBe(true);
    expect(
      skillSuggestionSchema.safeParse({ slug: "x", label: "x", color: "abcdef" }).success,
    ).toBe(false);
  });
});

describe("skillSearchResponseSchema", () => {
  it("accepts an empty list", () => {
    const r = skillSearchResponseSchema.safeParse({ items: [] });
    expect(r.success).toBe(true);
  });
});
