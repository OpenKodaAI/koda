import { describe, expect, it } from "vitest";
import { parseQualityCockpit } from "@/lib/contracts/quality-cockpit";

const qualityCockpitPayload = {
  schema_version: "quality_cockpit.v1",
  generated_at: "2026-05-19T16:00:00Z",
  status: "warning",
  summary: {
    success_rate: 0.92,
    failure_count: 3,
    run_count: 120,
    cost_usd: 12.45,
    timeout_rate: 0.04,
    eval_trend: "flat",
    eval_score: 0.88,
  },
  groups: [
    {
      entity_type: "agent",
      label: "Agents",
      status: "warning",
      metrics: { success_rate: 0.9, failure_count: 2, run_count: 80, timeout_rate: 0.03 },
      items: [
        {
          entity_type: "agent",
          entity_id: "FE",
          label: "Frontend",
          status: "degraded",
          risk_class: "medium",
          metrics: {
            success_rate: 0.81,
            failure_count: 2,
            run_count: 40,
            cost_usd: 6.25,
            timeout_rate: 0.1,
            eval_trend: "regressing",
          },
          failures: [
            {
              failure_id: "failure:route-timeout",
              status: "degraded",
              risk_class: "high",
              title: "Route timeout",
              summary: "Specialist timed out before coordinator synthesis.",
              count: 2,
              run_graph_node_ids: ["reply_obligation:7", "coordinator_synthesis:9"],
              proposal_id: "proposal:route-timeout",
              proposal_action_available: true,
            },
          ],
          release_gate_ids: ["run_graph_completeness"],
          improvement_proposal_ids: ["proposal:route-timeout"],
        },
      ],
    },
    {
      entity_type: "route_source",
      label: "Route sources",
      status: "healthy",
      items: [
        {
          entity_type: "route_source",
          entity_id: "semantic",
          label: "Semantic router",
          status: "healthy",
          risk_class: "low",
          metrics: { success_rate: 0.96, failure_count: 0, run_count: 55, timeout_rate: 0.01 },
        },
      ],
    },
  ],
  top_failures: [
    {
      failure_id: "failure:route-timeout",
      status: "degraded",
      risk_class: "high",
      title: "Route timeout",
      count: 2,
      proposal_action_available: true,
    },
  ],
  route_quality_history: [
    {
      schema_version: "route_outcome.v1",
      route_source: "semantic",
      outcome_count: 2,
      success_rate: 0.5,
      timeout_rate: 0.5,
      failure_rate: 0.5,
      quality_score: 0.5,
      run_graph_node_ids: ["agent_request:1"],
    },
  ],
  release_blockers: [
    {
      schema_version: "release_blocker.v1",
      blocker_id: "release-blocker:1",
      gate_id: "run_graph_completeness",
      severity: "high",
      status: "failing",
      title: "RunGraph completeness",
      summary: "Missing synthesis path.",
      next_action: "Inspect RunGraph completeness failures.",
      proposal_action_available: true,
    },
  ],
  release_quality_ref: "release_quality:latest",
  trajectory_export_refs: ["trajectory_export:1"],
};

describe("quality cockpit contracts", () => {
  it("parses backend-shaped quality_cockpit.v1 payloads", () => {
    const cockpit = parseQualityCockpit(qualityCockpitPayload);

    expect(cockpit).toMatchObject({
      schema_version: "quality_cockpit.v1",
      status: "warning",
      release_quality_ref: "release_quality:latest",
    });
    expect(cockpit?.groups.map((group) => group.entity_type)).toEqual(["agent", "route_source"]);
    expect(cockpit?.groups[0]?.items[0]?.failures[0]?.proposal_id).toBe("proposal:route-timeout");
    expect(cockpit?.route_quality_history[0]?.route_source).toBe("semantic");
    expect(cockpit?.release_blockers[0]?.gate_id).toBe("run_graph_completeness");
  });

  it("rejects invalid statuses instead of reclassifying them", () => {
    const cockpit = parseQualityCockpit({
      ...qualityCockpitPayload,
      status: "passing",
    });

    expect(cockpit).toBeNull();
  });

  it("rejects invalid risk classes instead of reclassifying them", () => {
    const cockpit = parseQualityCockpit({
      ...qualityCockpitPayload,
      groups: [
        {
          entity_type: "tool",
          label: "Tools",
          status: "warning",
          items: [
            {
              entity_type: "tool",
              entity_id: "shell",
              label: "Shell",
              status: "warning",
              risk_class: "destructive_write",
              metrics: { success_rate: 0.7, failure_count: 1, run_count: 4, timeout_rate: 0 },
            },
          ],
        },
      ],
    });

    expect(cockpit).toBeNull();
  });

  it("rejects reclassified failure risks", () => {
    const cockpit = parseQualityCockpit({
      ...qualityCockpitPayload,
      top_failures: [
        {
          failure_id: "failure:unsafe",
          status: "blocked",
          risk_class: "safe_enough",
          title: "Unsafe write",
        },
      ],
    });

    expect(cockpit).toBeNull();
  });
});
