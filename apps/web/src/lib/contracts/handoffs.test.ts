import { describe, expect, it } from "vitest";
import {
  parseHandoffEvent,
  parseHandoffEvents,
  parseRouteExplanation,
} from "@/lib/contracts/handoffs";
import { parseRunGraphSnapshot } from "@/lib/contracts/run-graph";

const routeExplanationPayload = {
  schema_version: "route_explanation.v1",
  route_id: "route:1",
  source: "semantic",
  status: "selected",
  selected_agent_ids: ["FE", "QA"],
  excluded_agent_ids: ["OPS"],
  confidence: 0.84,
  reason: "FE and QA matched task capability and quality history.",
  candidates: [
    {
      agent_id: "FE",
      status: "selected",
      rank: 1,
      score: 0.91,
      confidence: 0.86,
      reason: "Best capability fit.",
      signals: [
        { name: "semantic_score", score: 0.92, weight: 0.5, direction: "positive" },
        { name: "load_score", score: 0.12, weight: 0.15, direction: "positive" },
      ],
    },
    {
      agent_id: "OPS",
      status: "excluded",
      exclusion_reason: "missing_required_tool",
      score: 0.41,
      reason: "Route required frontend write access.",
    },
  ],
  run_graph_node_id: "handoff_event:1",
};

describe("handoff contracts", () => {
  it("parses backend-shaped handoff_event.v1 payloads", () => {
    const event = parseHandoffEvent({
      schema_version: "handoff_event.v1",
      handoff_id: "handoff:1",
      source_agent_id: "PM",
      destination_agent_ids: ["FE", "QA"],
      reason: "Need implementation and review before synthesis.",
      handoff_kind: "parallel_consult",
      context_policy: "summary",
      deadline: "2026-05-19T15:30:00Z",
      return_criteria: ["Return implementation notes.", "Declare blockers or timeout."],
      status: "requested",
      active_agent_id: "PM",
      coordinator_agent_id: "PM",
      thread_id: "thread:1",
      squad_id: "squad:alpha",
      run_graph_node_id: "handoff_event:1",
      route_explanation: routeExplanationPayload,
      transcript_refs: ["room-message:1"],
      artifact_refs: ["artifact:plan"],
      metadata: { parallel: true },
      created_at: "2026-05-19T15:00:00Z",
    });

    expect(event).toMatchObject({
      schema_version: "handoff_event.v1",
      handoff_id: "handoff:1",
      handoff_kind: "parallel_consult",
      status: "requested",
      destination_agent_ids: ["FE", "QA"],
      run_graph_node_id: "handoff_event:1",
    });
    expect(event?.route_explanation?.candidates[1]?.exclusion_reason).toBe("missing_required_tool");
  });

  it("parses handoff_event.v1 lists", () => {
    const items = parseHandoffEvents({
      schema_version: "handoff_event.v1",
      items: [
        {
          schema_version: "handoff_event.v1",
          handoff_id: "handoff:2",
          source_agent_id: "FE",
          destination_agent_ids: ["PM"],
          reason: "Return completed implementation.",
          handoff_kind: "return",
          context_policy: "artifact_refs",
          return_criteria: ["Coordinator can synthesize."],
          status: "returned",
          run_graph_node_id: "handoff_event:2",
        },
      ],
    });

    expect(items).toHaveLength(1);
    expect(items[0]?.handoff_kind).toBe("return");
  });

  it("rejects invalid handoff statuses instead of reclassifying them", () => {
    const event = parseHandoffEvent({
      schema_version: "handoff_event.v1",
      handoff_id: "handoff:3",
      source_agent_id: "PM",
      destination_agent_ids: ["FE"],
      reason: "Need help.",
      handoff_kind: "consult",
      context_policy: "summary",
      return_criteria: ["Reply."],
      status: "done_enough",
      run_graph_node_id: "handoff_event:3",
    });

    expect(event).toBeNull();
  });

  it("parses route_explanation.v1 payloads and rejects invalid candidate statuses", () => {
    expect(parseRouteExplanation(routeExplanationPayload)?.selected_agent_ids).toEqual(["FE", "QA"]);
    expect(
      parseRouteExplanation({
        ...routeExplanationPayload,
        candidates: [{ agent_id: "FE", status: "maybe", reason: "Ambiguous." }],
      }),
    ).toBeNull();
  });

  it("preserves handoff_event RunGraph nodes from backend-shaped snapshots", () => {
    const graph = parseRunGraphSnapshot({
      schema_version: "run_graph.v1",
      graph_id: "graph:handoff",
      agent_id: "PM",
      task_id: 42,
      summary: { status: "completed", node_count: 1, edge_count: 0 },
      nodes: [
        {
          node_id: "handoff_event:1",
          node_type: "handoff_event",
          status: "completed",
          agent_id: "PM",
          task_id: 42,
          summary: "Parallel consult requested for FE and QA.",
          payload: { handoff_id: "handoff:1" },
        },
      ],
    });

    expect(graph?.nodes[0]?.type).toBe("handoff_event");
  });
});
