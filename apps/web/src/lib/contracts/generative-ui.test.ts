import { describe, expect, it } from "vitest";
import {
  generativeBlockSchema,
  parseGenerativeBlock,
  parseGenerativeBlockEnvelope,
  uiFormFieldSchema,
} from "@/lib/contracts/generative-ui";

const validUiCard = {
  id: "card_1",
  version: 1 as const,
  block_type: "ui_card" as const,
  payload: {
    title: "Latest deploy",
    body: "Build #42 succeeded.",
  },
};

const validUiCallout = {
  id: "cal_1",
  version: 1 as const,
  block_type: "ui_callout" as const,
  payload: {
    tone: "warning" as const,
    body: "Heads up: rate limit at 80%.",
  },
};

const validUiSteps = {
  id: "steps_1",
  version: 1 as const,
  block_type: "ui_steps" as const,
  payload: {
    items: [
      { id: "1", label: "Plan", status: "done" as const },
      { id: "2", label: "Apply", status: "running" as const },
    ],
  },
};

const validUiTable = {
  id: "tbl_1",
  version: 1 as const,
  block_type: "ui_table" as const,
  payload: {
    columns: [
      { key: "name", label: "Name" },
      { key: "cost", label: "Cost", format: "cost" as const },
    ],
    rows: [{ name: "alpha", cost: 0.04 }],
  },
};

const validUiChart = {
  id: "ch_1",
  version: 1 as const,
  block_type: "ui_chart" as const,
  payload: {
    kind: "line" as const,
    x_key: "ts",
    y_keys: ["count"],
    data: [{ ts: "00", count: 1 }, { ts: "01", count: 5 }],
  },
};

const validUiForm = {
  id: "form_1",
  version: 1 as const,
  block_type: "ui_form" as const,
  payload: {
    fields: [
      { kind: "text" as const, id: "name", label: "Name" },
      { kind: "select" as const, id: "env", label: "Env", options: [{ value: "p", label: "Prod" }] },
    ],
  },
};

const validUiChoice = {
  id: "ch_1",
  version: 1 as const,
  block_type: "ui_choice" as const,
  payload: {
    prompt: "Pick one",
    options: [
      { id: "a", label: "Alpha" },
      { id: "b", label: "Beta" },
    ],
  },
};

describe("generativeBlockSchema", () => {
  it.each([
    ["ui_card", validUiCard],
    ["ui_callout", validUiCallout],
    ["ui_steps", validUiSteps],
    ["ui_table", validUiTable],
    ["ui_chart", validUiChart],
    ["ui_form", validUiForm],
    ["ui_choice", validUiChoice],
  ])("validates a %s block", (_name, raw) => {
    const r = generativeBlockSchema.safeParse(raw);
    expect(r.success).toBe(true);
  });

  it("defaults state to 'complete' when omitted", () => {
    const r = generativeBlockSchema.safeParse(validUiCard);
    expect(r.success).toBe(true);
    if (r.success) expect(r.data.state).toBe("complete");
  });

  it("rejects an unknown block_type", () => {
    const r = generativeBlockSchema.safeParse({
      ...validUiCard,
      block_type: "ui_unknown",
    });
    expect(r.success).toBe(false);
  });

  it("rejects ui_card payload missing title", () => {
    const r = generativeBlockSchema.safeParse({
      ...validUiCard,
      payload: { body: "no title" },
    });
    expect(r.success).toBe(false);
  });

  it("rejects ui_table with too many columns", () => {
    const r = generativeBlockSchema.safeParse({
      ...validUiTable,
      payload: {
        ...validUiTable.payload,
        columns: Array.from({ length: 13 }, (_, i) => ({
          key: `c${i}`,
          label: `c${i}`,
        })),
      },
    });
    expect(r.success).toBe(false);
  });

  it("rejects ui_choice with fewer than 2 options", () => {
    const r = generativeBlockSchema.safeParse({
      ...validUiChoice,
      payload: { ...validUiChoice.payload, options: [{ id: "a", label: "A" }] },
    });
    expect(r.success).toBe(false);
  });

  it("rejects ui_card footer_action with malformed link href", () => {
    const r = generativeBlockSchema.safeParse({
      ...validUiCard,
      payload: {
        ...validUiCard.payload,
        footer_actions: [
          {
            id: "open",
            label: "Open",
            action: { kind: "link", href: "not-a-url" },
          },
        ],
      },
    });
    expect(r.success).toBe(false);
  });
});

describe("parseGenerativeBlock", () => {
  it("returns the block on success", () => {
    expect(parseGenerativeBlock(validUiCard)?.block_type).toBe("ui_card");
  });
  it("returns null on failure", () => {
    expect(parseGenerativeBlock({ id: "x", version: 1, block_type: "nope", payload: {} })).toBeNull();
  });
});

describe("parseGenerativeBlockEnvelope", () => {
  it("parses streaming envelopes without requiring full payload", () => {
    const env = parseGenerativeBlockEnvelope({
      block_type: "ui_table",
      state: "streaming",
    });
    expect(env).not.toBeNull();
    expect(env?.block_type).toBe("ui_table");
    expect(env?.state).toBe("streaming");
  });
  it("rejects non-objects", () => {
    expect(parseGenerativeBlockEnvelope(null)).toBeNull();
    expect(parseGenerativeBlockEnvelope("nope")).toBeNull();
  });
});

describe("uiFormFieldSchema", () => {
  it("validates each field kind", () => {
    expect(uiFormFieldSchema.safeParse({ kind: "text", id: "n", label: "Name" }).success).toBe(true);
    expect(uiFormFieldSchema.safeParse({ kind: "toggle", id: "ok", label: "Ok" }).success).toBe(true);
    expect(uiFormFieldSchema.safeParse({ kind: "number", id: "x", label: "X" }).success).toBe(true);
  });

  it("rejects select with empty options", () => {
    expect(
      uiFormFieldSchema.safeParse({ kind: "select", id: "e", label: "E", options: [] }).success,
    ).toBe(false);
  });
});
