import { describe, expect, it } from "vitest";
import { queryKeys } from "@/lib/query/keys";

describe("queryKeys", () => {
  it("normalizes bot ids for executions filters", () => {
    expect(
      queryKeys.dashboard.executions({
        botIds: ["KODA", "ATLAS"],
        status: "running",
      }),
    ).toEqual([
      "dashboard",
      "executions",
      {
        botIds: ["ATLAS", "KODA"],
        status: "running",
      },
    ]);
  });

  it("keeps session detail keys stable", () => {
    expect(queryKeys.dashboard.sessionDetail("KODA", "session-1")).toEqual([
      "dashboard",
      "sessions",
      "KODA",
      "session-1",
    ]);
  });
});
