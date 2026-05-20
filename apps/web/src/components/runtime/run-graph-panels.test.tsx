import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  ChildRunsPanel,
  ContextGovernancePanel,
  HandoffTimelinePanel,
  RouteExplanationPanel,
  RunGraphSummaryPanel,
  RunGraphViewer,
  RunReplayPanel,
} from "@/components/runtime/run-graph-panels";
import { SandboxDoctorPanel } from "@/components/runtime/sandbox-doctor-panel";
import {
  phase2DoctorFixture,
  phase2RunGraphFixture,
  phase2RunReplayFixture,
} from "@/lib/contracts/__fixtures__/phase2";

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

describe("RunGraph panels", () => {
  it("renders fixture-driven RunGraph summary, viewer, and replay", () => {
    const { container } = render(
      <div>
        <RunGraphSummaryPanel
          graph={phase2RunGraphFixture}
          replay={phase2RunReplayFixture}
          releaseQuality={{
            schema_version: "release_quality.v1",
            agent_id: "ATLAS",
            status: "blocked",
            generated_at: "2026-05-17T10:00:00Z",
            gates: [
              {
                id: "run_graph_completeness",
                title: "RunGraph completeness",
                status: "blocked",
                summary: "Missing policy_gate node.",
                required: true,
              },
            ],
            metrics: {
              run_graph_warnings: ["Missing policy_gate node."],
            },
            top_failures: [],
          }}
          runtimeHref="/runtime/ATLAS/tasks/42"
        />
        <RunGraphViewer graph={phase2RunGraphFixture} />
        <RouteExplanationPanel
          graph={{
            ...phase2RunGraphFixture,
            nodes: [
              ...phase2RunGraphFixture.nodes,
              {
                id: "agent_request:route",
                type: "agent_request",
                label: "Route",
                status: "completed",
                metadata: {
                  route_explanation: {
                    schema_version: "route_explanation.v1",
                    source: "semantic",
                    status: "selected",
                    selected_agent_ids: ["FE"],
                    excluded_agent_ids: ["OPS"],
                    confidence: 0.84,
                    required_tools: ["read_file"],
                    required_skills: ["react-build"],
                    summary: "Selected FE from quality history.",
                    candidates: [
                      {
                        agent_id: "FE",
                        status: "selected",
                        score: 0.91,
                        reason: "Best fit.",
                      },
                      {
                        agent_id: "OPS",
                        status: "excluded",
                        exclusion_reason: "missing_required_tool",
                      },
                    ],
                  },
                },
              },
            ],
          }}
        />
        <HandoffTimelinePanel
          graph={{
            ...phase2RunGraphFixture,
            nodes: [
              ...phase2RunGraphFixture.nodes,
              {
                id: "handoff_event:1",
                type: "handoff_event",
                label: "Parallel consult",
                status: "completed",
                metadata: {
                  handoff_event: {
                    schema_version: "handoff_event.v1",
                    handoff_id: "handoff:1",
                    source_agent_id: "PM",
                    destination_agent_ids: ["FE", "QA"],
                    reason: "Need implementation and verification.",
                    handoff_kind: "parallel_consult",
                    context_policy: "summary",
                    return_criteria: ["Reply with completed evidence."],
                    status: "returned",
                    run_graph_node_id: "handoff_event:1",
                  },
                },
              },
            ],
          }}
        />
        <ChildRunsPanel
          agentId="ATLAS"
          childRuns={[
            {
              schema_version: "child_run.v1",
              child_run_id: "childrun_123",
              agent_id: "ATLAS",
              parent_task_id: 42,
              child_task_id: 43,
              status: "completed",
              toolset: "read_only",
              summary: "Child inspected the contract",
              artifacts: [],
              warnings: [],
              available_actions: ["open_execution"],
            },
          ]}
        />
        <ContextGovernancePanel
          context={{
            schema_version: "context_governance.v1",
            summary: {
              block_count: 2,
              included_count: 2,
              dropped_count: 0,
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
              {
                schema_version: "context_governance.v1",
                block_id: "memory:recall",
                category: "memory",
                source: "memory_recall",
                token_estimate: 0,
                status: "included",
                redaction: "metadata_only",
                risk: "memory",
                provenance: {
                  selected_count: 2,
                  dropped_count: 1,
                  conflict_count: 1,
                  trust_score: 0.72,
                  dropped_reasons: { stale: 1 },
                  explanations: [
                    {
                      memory_id: 10,
                      layer: "episodic",
                      sensitivity: "normal",
                    },
                  ],
                },
              },
            ],
          }}
        />
        <RunReplayPanel replay={phase2RunReplayFixture} />
      </div>,
    );

    expect(screen.getByText("run_graph.v1")).toBeInTheDocument();
    expect(screen.getByText("Task completed with policy, tool, artifact, and cost nodes.")).toBeInTheDocument();
    expect(screen.getByText(/RunGraph completeness:/)).toBeInTheDocument();
    expect(screen.getAllByText(/Missing policy_gate node/).length).toBeGreaterThan(0);
    expect(screen.getByText("Run tree")).toBeInTheDocument();
    expect(screen.getByText("Route explanation")).toBeInTheDocument();
    expect(screen.getByText("Selected FE from quality history.")).toBeInTheDocument();
    expect(screen.getByText("Handoff timeline")).toBeInTheDocument();
    expect(screen.getByText("PM -> FE, QA")).toBeInTheDocument();
    expect(screen.getAllByText("Policy gate").length).toBeGreaterThan(0);
    expect(screen.getByText("Delegate Task children")).toBeInTheDocument();
    expect(screen.getByText("Context governance")).toBeInTheDocument();
    expect(screen.getByText("selected 2")).toBeInTheDocument();
    expect(screen.getByText("dropped: stale:1")).toBeInTheDocument();
    expect(screen.getByText("10 · episodic · normal")).toBeInTheDocument();
    expect(screen.getByText("Offline replay available")).toBeInTheDocument();
    expect(screen.getByText("Sandbox policy gate")).toBeInTheDocument();
    expect(screen.getByLabelText("Tool call node")).toBeInTheDocument();
    expect(container.querySelector('[data-node-visual="queue_wait"]')).toBeInTheDocument();
    expect(container.querySelector('[data-node-visual="policy_gate"]')).toBeInTheDocument();
    expect(container.querySelector('[data-node-visual="tool_call"]')).toBeInTheDocument();
    expect(container.querySelector('[data-replay-visual="tool_call"]')).toBeInTheDocument();
  });

  it("renders unavailable states without requiring mocks", () => {
    render(
      <div>
        <RunGraphSummaryPanel graph={null} replay={null} />
        <RunGraphViewer graph={null} />
        <RouteExplanationPanel graph={null} />
        <HandoffTimelinePanel graph={null} />
        <RunReplayPanel replay={null} />
      </div>,
    );

    expect(screen.getByText("RunGraph unavailable")).toBeInTheDocument();
    expect(screen.getByText("No RunGraph snapshot")).toBeInTheDocument();
    expect(screen.getByText("Graph viewer unavailable")).toBeInTheDocument();
    expect(screen.getByText("Route explanation unavailable")).toBeInTheDocument();
    expect(screen.getByText("No handoff timeline")).toBeInTheDocument();
    expect(screen.getByText("Replay unavailable")).toBeInTheDocument();
  });
});

describe("SandboxDoctorPanel", () => {
  it("renders degraded doctor results and unavailable fallback", () => {
    const { rerender } = render(<SandboxDoctorPanel result={phase2DoctorFixture} />);

    expect(screen.getByText("sandbox_doctor.v1")).toBeInTheDocument();
    expect(screen.getByText(/Sandbox doctor degraded/)).toBeInTheDocument();
    expect(screen.getByText("Browser runtime")).toBeInTheDocument();
    expect(screen.getByText("Degraded: browser")).toBeInTheDocument();

    rerender(<SandboxDoctorPanel result={null} />);

    expect(screen.getByText("Sandbox doctor unavailable")).toBeInTheDocument();
    expect(screen.getByText("No sandbox_doctor.v1 result is published for this task.")).toBeInTheDocument();
  });
});
