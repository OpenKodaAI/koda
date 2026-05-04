import { describe, expect, it } from "vitest";
import {
  blockSubmitBodySchema,
  composerCommandSchema,
  isSessionStreamEvent,
  mentionSchema,
  messageChunkPayloadSchema,
  parseSessionStreamEvent,
  sendSessionMessageBodySchema,
} from "@/lib/contracts/sessions";

describe("mentionSchema", () => {
  it("accepts well-formed skill and mcp slugs", () => {
    expect(mentionSchema.safeParse({ kind: "skill", slug: "python_dev" }).success).toBe(true);
    expect(mentionSchema.safeParse({ kind: "mcp", slug: "supabase-cloud" }).success).toBe(true);
  });

  it("rejects uppercase, spaces, and over-length slugs", () => {
    expect(mentionSchema.safeParse({ kind: "skill", slug: "Python" }).success).toBe(false);
    expect(mentionSchema.safeParse({ kind: "skill", slug: "py dev" }).success).toBe(false);
    expect(mentionSchema.safeParse({ kind: "skill", slug: "x".repeat(65) }).success).toBe(false);
  });

  it("rejects unknown kinds", () => {
    expect(mentionSchema.safeParse({ kind: "tool", slug: "anything" }).success).toBe(false);
  });
});

describe("composerCommandSchema", () => {
  it("requires a non-empty id", () => {
    expect(composerCommandSchema.safeParse({ id: "" }).success).toBe(false);
    expect(composerCommandSchema.safeParse({ id: "new-session" }).success).toBe(true);
  });

  it("accepts optional payload as record", () => {
    const r = composerCommandSchema.safeParse({ id: "switch-agent", payload: { agent_id: "x" } });
    expect(r.success).toBe(true);
  });
});

describe("sendSessionMessageBodySchema", () => {
  it("accepts a minimal body", () => {
    const r = sendSessionMessageBodySchema.safeParse({ text: "Hello" });
    expect(r.success).toBe(true);
  });

  it("accepts mentions and command", () => {
    const r = sendSessionMessageBodySchema.safeParse({
      text: "Investigate using @[skill:python_dev]",
      mentions: [{ kind: "skill", slug: "python_dev" }],
      command: { id: "switch-agent", payload: { agent_id: "BOT1" } },
    });
    expect(r.success).toBe(true);
  });

  it("rejects empty text and over-long mention arrays", () => {
    expect(sendSessionMessageBodySchema.safeParse({ text: "" }).success).toBe(false);
    const tooMany = Array.from({ length: 17 }, () => ({ kind: "skill" as const, slug: "x" }));
    const r = sendSessionMessageBodySchema.safeParse({ text: "Hi", mentions: tooMany });
    expect(r.success).toBe(false);
  });

  it("trims whitespace and enforces 10k char cap", () => {
    const r = sendSessionMessageBodySchema.safeParse({
      text: "  hello  ",
    });
    expect(r.success).toBe(true);
    if (r.success) expect(r.data.text).toBe("hello");

    expect(
      sendSessionMessageBodySchema.safeParse({ text: "x".repeat(10_001) }).success,
    ).toBe(false);
  });
});

describe("blockSubmitBodySchema", () => {
  it("accepts string/number/bool/null/array values", () => {
    const r = blockSubmitBodySchema.safeParse({
      block_type: "ui_form",
      values: {
        name: "Ryan",
        age: 30,
        ok: true,
        nullable: null,
        tags: ["alpha", "beta"],
      },
      action_id: "submit",
    });
    expect(r.success).toBe(true);
  });

  it("rejects nested objects in values", () => {
    const r = blockSubmitBodySchema.safeParse({
      block_type: "ui_choice",
      values: { picked: { id: "a" } },
    });
    expect(r.success).toBe(false);
  });

  it("rejects unknown block_type", () => {
    const r = blockSubmitBodySchema.safeParse({
      block_type: "ui_unknown",
      values: {},
    });
    expect(r.success).toBe(false);
  });
});

describe("parseSessionStreamEvent", () => {
  it("parses a well-formed envelope", () => {
    const e = parseSessionStreamEvent({
      seq: 1,
      type: "message_chunk",
      task_id: 42,
      payload: { delta: "Hel" },
    });
    expect(e).not.toBeNull();
    expect(e?.type).toBe("message_chunk");
    expect(e?.payload).toEqual({ delta: "Hel" });
  });

  it("returns null when seq is missing", () => {
    expect(parseSessionStreamEvent({ type: "heartbeat", task_id: null })).toBeNull();
  });

  it("preserves passthrough fields and defaults nullable optionals", () => {
    const e = parseSessionStreamEvent({
      seq: 5,
      type: "task_complete",
      task_id: null,
      ts: "2026-05-02T00:00:00Z",
    });
    expect(e?.payload).toEqual({});
    expect(e?.env_id).toBeNull();
    expect(e?.resource_snapshot_ref).toBeNull();
  });

  it("isSessionStreamEvent matches the same shape contract", () => {
    expect(
      isSessionStreamEvent({ seq: 0, type: "heartbeat", task_id: null, payload: {} }),
    ).toBe(true);
    expect(isSessionStreamEvent({ seq: "0", type: "x", task_id: null })).toBe(false);
  });
});

describe("messageChunkPayloadSchema", () => {
  it("accepts delta with optional message_id and block_id", () => {
    expect(messageChunkPayloadSchema.safeParse({ delta: "" }).success).toBe(true);
    expect(
      messageChunkPayloadSchema.safeParse({
        delta: "tok",
        message_id: "m_1",
        block_id: "b_1",
      }).success,
    ).toBe(true);
  });

  it("rejects missing delta", () => {
    expect(messageChunkPayloadSchema.safeParse({ message_id: "m_1" }).success).toBe(false);
  });
});
