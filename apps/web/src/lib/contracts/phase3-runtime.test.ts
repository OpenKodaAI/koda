import { describe, expect, it } from "vitest";
import {
  parseChildRuns,
  parseContextGovernancePayload,
} from "@/lib/contracts/phase3-runtime";

describe("Phase 3 runtime contracts", () => {
  it("parses child_run.v1 records", () => {
    const childRuns = parseChildRuns([
      {
        schema_version: "child_run.v1",
        child_run_id: "childrun_123",
        agent_id: "KODA",
        parent_task_id: 41,
        child_task_id: 42,
        status: "running",
        target_agent_id: "KODA",
        toolset: "read_only",
        summary: "Inspect files",
        artifacts: [],
        warnings: [],
        available_actions: ["cancel", "interrupt", "open_execution"],
      },
    ]);

    expect(childRuns).toHaveLength(1);
    expect(childRuns[0]?.child_task_id).toBe(42);
    expect(childRuns[0]?.available_actions).toContain("interrupt");
  });

  it("parses context_governance.v1 summaries", () => {
    const context = parseContextGovernancePayload({
      schema_version: "context_governance.v1",
      summary: {
        block_count: 2,
        included_count: 1,
        dropped_count: 1,
        review_required_count: 0,
      },
      blocks: [
        {
          schema_version: "context_governance.v1",
          block_id: "immutable_base_policy",
          category: "base",
          source: "default",
          token_estimate: 100,
          status: "included",
          redaction: "strict",
          risk: "low",
          provenance: {},
        },
      ],
    });

    expect(context?.schema_version).toBe("context_governance.v1");
    expect(context?.summary.included_count).toBe(1);
    expect(context?.blocks[0]?.block_id).toBe("immutable_base_policy");
  });
});
