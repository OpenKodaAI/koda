import { describe, expect, it } from "vitest";
import { parseMcpCapabilityRisk } from "@/lib/contracts/mcp-risk";
import { parseRunGraphSnapshot, parseRunReplayPlan } from "@/lib/contracts/run-graph";
import { parseSandboxDoctorResult } from "@/lib/contracts/sandbox-doctor";
import {
  phase2DoctorFixture,
  phase2McpRiskFixture,
  phase2RunGraphFixture,
  phase2RunReplayFixture,
} from "@/lib/contracts/__fixtures__/phase2";

describe("Phase 2 runtime contracts", () => {
  it("parses versioned RunGraph and replay fixtures", () => {
    const graph = parseRunGraphSnapshot(phase2RunGraphFixture);
    const replay = parseRunReplayPlan(phase2RunReplayFixture);

    expect(graph?.run_graph_version).toBe("run_graph.v1");
    expect(graph?.status).toBe("completed");
    expect(graph?.nodes.some((node) => node.type === "policy_gate")).toBe(true);
    expect(replay?.replay_version).toBe("run_replay.v1");
    expect(replay?.provider_calls_disabled).toBe(true);
  });

  it("accepts stalled and degraded run states", () => {
    const graph = parseRunGraphSnapshot({
      ...phase2RunGraphFixture,
      status: "degraded",
      nodes: [
        {
          ...phase2RunGraphFixture.nodes[0],
          id: "node_stalled",
          status: "stalled",
        },
      ],
    });

    expect(graph?.status).toBe("degraded");
    expect(graph?.nodes[0]?.status).toBe("stalled");
  });

  it("normalizes backend RunGraph and replay payloads", () => {
    const graph = parseRunGraphSnapshot({
      schema_version: "run_graph.v1",
      graph_id: "run:KODA:42:attempt:1",
      agent_id: "KODA",
      task_id: 42,
      attempt: 1,
      summary: { status: "completed", node_count: 2, edge_count: 1 },
      nodes: [
        {
          node_id: "model_call:1:abc",
          node_type: "model_call",
          status: "info",
          summary: "Model turn",
          agent_id: "KODA",
          task_id: 42,
          attempt: 1,
          ordinal: 1,
          payload: { query_hash: "abc" },
        },
        {
          node_id: "tool_result:2:def",
          parent_node_id: "model_call:1:abc",
          node_type: "tool_result",
          status: "completed",
          summary: "Tool result",
          agent_id: "KODA",
          task_id: 42,
          attempt: 1,
          ordinal: 2,
        },
      ],
      edges: [],
    });
    const replay = parseRunReplayPlan({
      schema_version: "run_replay.v1",
      graph_id: "run:KODA:42:attempt:1",
      task_id: 42,
      replay_mode: "offline",
      generated_at: "2026-05-16T14:10:00.000Z",
      model_outputs: [{ response_hash: "abc" }],
      tool_results: [{ tool: "read_file" }],
      divergences: [],
    });

    expect(graph?.run_graph_version).toBe("run_graph.v1");
    expect(graph?.nodes.map((node) => node.type)).toEqual(["model_call", "tool_result"]);
    expect(graph?.nodes[0]?.status).toBe("completed");
    expect(replay?.mode).toBe("offline");
    expect(replay?.steps.some((step) => step.type === "tool_result")).toBe(true);
  });

  it("rejects unversioned RunGraph payloads", () => {
    expect(parseRunGraphSnapshot({ ...phase2RunGraphFixture, run_graph_version: "run_graph" })).toBeNull();
    expect(parseRunReplayPlan({ ...phase2RunReplayFixture, mode: "provider" })).toBeNull();
  });

  it("parses sandbox doctor and MCP risk fixtures", () => {
    const doctor = parseSandboxDoctorResult(phase2DoctorFixture);
    const risk = parseMcpCapabilityRisk(phase2McpRiskFixture);

    expect(doctor?.doctor_version).toBe("sandbox_doctor.v1");
    expect(doctor?.status).toBe("degraded");
    expect(risk?.taxonomy_version).toBe("mcp_risk.v1");
    expect(risk?.risk_class).toBe("destructive_write");
  });
});
