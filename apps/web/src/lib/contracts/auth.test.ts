import { describe, expect, it } from "vitest";

import "@/lib/contracts/auth";
import { resolveBodySchema } from "@/lib/contracts/proxy-body-schemas";

describe("auth proxy body schemas", () => {
  it("normalizes valid operator profile updates", () => {
    const schema = resolveBodySchema("PATCH", ["auth", "profile"]);

    expect(schema?.parse({ display_name: "  Avery   Stone  " })).toEqual({
      display_name: "Avery Stone",
    });
  });

  it("rejects invalid operator profile updates", () => {
    const schema = resolveBodySchema("PATCH", ["auth", "profile"]);

    expect(() => schema?.parse({ display_name: "   " })).toThrow();
    expect(() => schema?.parse({ display_name: "Bad\nName" })).toThrow();
    expect(() => schema?.parse({ display_name: "A".repeat(81) })).toThrow();
  });
});
