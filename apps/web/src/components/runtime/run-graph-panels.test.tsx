import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  ChildRunsPanel,
  ContextGovernancePanel,
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
          runtimeHref="/runtime/ATLAS/tasks/42"
        />
        <RunGraphViewer graph={phase2RunGraphFixture} />
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
              block_count: 1,
              included_count: 1,
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
            ],
          }}
        />
        <RunReplayPanel replay={phase2RunReplayFixture} />
      </div>,
    );

    expect(screen.getByText("run_graph.v1")).toBeInTheDocument();
    expect(screen.getByText("Task completed with policy, tool, artifact, and cost nodes.")).toBeInTheDocument();
    expect(screen.getByText("Run tree")).toBeInTheDocument();
    expect(screen.getAllByText("Policy gate").length).toBeGreaterThan(0);
    expect(screen.getByText("Delegate Task children")).toBeInTheDocument();
    expect(screen.getByText("Context governance")).toBeInTheDocument();
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
        <RunReplayPanel replay={null} />
      </div>,
    );

    expect(screen.getByText("RunGraph unavailable")).toBeInTheDocument();
    expect(screen.getByText("No RunGraph snapshot")).toBeInTheDocument();
    expect(screen.getByText("Graph viewer unavailable")).toBeInTheDocument();
    expect(screen.getByText("Replay unavailable")).toBeInTheDocument();
  });
});

describe("SandboxDoctorPanel", () => {
  it("renders degraded doctor results and unavailable fallback", () => {
    const { rerender } = render(<SandboxDoctorPanel result={phase2DoctorFixture} />);

    expect(screen.getByText("sandbox_doctor.v1")).toBeInTheDocument();
    expect(screen.getByText("Sandbox doctor degraded")).toBeInTheDocument();
    expect(screen.getByText("Browser runtime")).toBeInTheDocument();
    expect(screen.getByText("Degraded: browser")).toBeInTheDocument();

    rerender(<SandboxDoctorPanel result={null} />);

    expect(screen.getByText("Sandbox doctor unavailable")).toBeInTheDocument();
    expect(screen.getByText("No sandbox_doctor.v1 result is published for this task.")).toBeInTheDocument();
  });
});
