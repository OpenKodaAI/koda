import { describe, expect, it } from "vitest";
import { queryKeys } from "@/lib/query/keys";

describe("queryKeys", () => {
  it("normalizes agent ids for executions filters", () => {
    expect(
      queryKeys.dashboard.executions({
        agentIds: ["KODA", "ATLAS"],
        status: "running",
      }),
    ).toEqual([
      "dashboard",
      "executions",
      {
        agentIds: ["ATLAS", "KODA"],
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
