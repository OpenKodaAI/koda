import { describe, expect, it } from "vitest";
import { z } from "zod";
import { createStorageCodec } from "@/lib/contracts/storage";

describe("createStorageCodec", () => {
  const codec = createStorageCodec("ui:test", z.object({ enabled: z.boolean() }), {
    enabled: false,
  });

  it("parses persisted values", () => {
    expect(codec.parse(JSON.stringify({ enabled: true }))).toEqual({ enabled: true });
  });

  it("falls back when persisted data is invalid", () => {
    expect(codec.parse("{bad json")).toEqual({ enabled: false });
    expect(codec.parse(JSON.stringify({ enabled: "yes" }))).toEqual({ enabled: false });
  });

  it("serializes validated values", () => {
    expect(codec.serialize({ enabled: true })).toBe('{"enabled":true}');
  });
});
