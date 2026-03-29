import { describe, expect, it } from "vitest";
import {
  buildRuntimeRoomRows,
  getRuntimeRowSummary,
  matchesRuntimeRoomFilter,
} from "@/lib/runtime-overview-model";
import type { RuntimeOverview } from "@/lib/runtime-types";

function overview(overrides: Partial<RuntimeOverview>): RuntimeOverview {
  return {
    botId: "ATLAS",
    botLabel: "ATLAS",
    botColor: "#ffffff",
    baseUrl: "http://localhost:8080",
    fetchedAt: "2026-03-19T00:00:00.000Z",
    health: null,
    snapshot: null,
    availability: {
      health: "available",
      database: "available",
      runtime: "available",
      browser: "available",
      attach: "available",
      errors: [],
    },
    queues: [],
    environments: [],
    incidents: [],
    activeTaskIds: [],
    retainedTaskIds: [],
    ...overrides,
  };
}

describe("buildRuntimeRoomRows", () => {
  it("does not dedupe queue rows across different bots with the same task id", () => {
    const rows = buildRuntimeRoomRows([
      overview({
        botId: "ATLAS",
        environments: [
          {
            id: 1,
            task_id: 17,
            status: "active",
            current_phase: "running",
            workspace_path: "/tmp/masp-17",
          },
        ],
      }),
      overview({
        botId: "NOVA",
        botLabel: "NOVA",
        queues: [
          {
            task_id: 17,
            status: "queued",
            query_text: "Second bot still has a queued task",
          },
        ],
      }),
    ]);

    expect(rows).toHaveLength(2);
    expect(rows.map((row) => `${row.botId}:${row.taskId}:${row.source}`)).toEqual([
      "ATLAS:17:environment",
      "NOVA:17:queue",
    ]);
  });

  it("propagates queue query text into environment rows", () => {
    const [row] = buildRuntimeRoomRows([
      overview({
        environments: [
          {
            id: 1,
            task_id: 42,
            status: "active",
            current_phase: "running",
            workspace_path: "/tmp/runtime-42",
          },
        ],
        queues: [
          {
            task_id: 42,
            status: "running",
            query_text: "Validate the runtime environment end-to-end",
          },
        ],
      }),
    ]);

    expect(row.queryText).toBe("Validate the runtime environment end-to-end");
    expect(getRuntimeRowSummary(row)).toContain("Validate the runtime environment");
  });

  it("keeps retrying rows visible in the active filter", () => {
    const [row] = buildRuntimeRoomRows([
      overview({
        queues: [
          {
            task_id: 8,
            status: "retrying",
            query_text: "Retry failed runtime task",
          },
        ],
      }),
    ]);

    expect(matchesRuntimeRoomFilter(row, "active")).toBe(true);
  });
});
