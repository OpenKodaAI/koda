import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import EvaluationsPageClient from "@/components/features/evaluations/evaluations-page-client";
import { AgentCatalogProvider } from "@/components/providers/agent-catalog-provider";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ToastNotification } from "@/components/ui/toast-notification";
import { ToastProvider } from "@/hooks/use-toast";
import { requestJson } from "@/lib/http-client";

vi.mock("@/lib/http-client", () => ({
  requestJson: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

vi.mock("@/hooks/use-create-agent", () => ({
  useCreateAgent: () => ({
    creating: false,
    createAgent: vi.fn(),
  }),
}));

const requestJsonMock = requestJson as unknown as ReturnType<typeof vi.fn>;

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider initialLanguage="en-US">
        <ToastProvider>
          <AgentCatalogProvider
            initialAgents={[
              {
                id: "ATLAS",
                label: "Atlas",
                color: "#D97757",
                colorRgb: "217, 119, 87",
              },
            ]}
          >
            <EvaluationsPageClient />
            <ToastNotification />
          </AgentCatalogProvider>
        </ToastProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("EvaluationsPageClient", () => {
  beforeEach(() => {
    requestJsonMock.mockReset();
    requestJsonMock.mockImplementation(async (path: string, init?: RequestInit) => {
      if (path.includes("/evals/cases") && init?.method === "PATCH") {
        return {
          schema_version: "eval_case.v1",
          case_key: "episode:42",
          agent_id: "ATLAS",
          title: "Tool regression smoke",
          status: "ready",
        };
      }
      if (path.endsWith("/evals/runs") && init?.method === "POST") {
        return {
          run: {
            schema_version: "eval_run.v1",
            run_id: "eval_run:next",
            agent_id: "ATLAS",
            mode: "offline",
            status: "queued",
            summary: { total: 1, passed: 0, failed: 0, warning: 0, skipped: 0, score: null },
          },
        };
      }
      if (path.endsWith("/evals/trajectory-exports")) {
        return {
          trajectory_export: {
            schema_version: "trajectory_export.v1",
            export_id: "export:1",
            agent_id: "ATLAS",
            run_id: "eval_run:1",
            status: "ready",
            format: "jsonl",
            replay_mode: "offline",
            redaction_applied: true,
            provider_calls_disabled: true,
            line_count: 8,
          },
        };
      }
      if (path.includes("/evals/cases")) {
        return {
          items: [
            {
              schema_version: "eval_case.v1",
              case_key: "episode:42",
              agent_id: "ATLAS",
              title: "Tool regression smoke",
              status: "ready",
              source: "run",
              source_task_id: 42,
              input_preview: "Check policy trace.",
              expected_output_preview: "Policy gate remains allow.",
              tool_expectations: [{ tool_id: "read_file" }],
              policy_expectations: [{ decision: "allow" }],
              created_at: "2026-05-17T10:00:00Z",
              updated_at: "2026-05-17T10:00:00Z",
            },
          ],
        };
      }
      if (path.includes("/evals/runs")) {
        return {
          items: [
            {
              schema_version: "eval_run.v1",
              run_id: "eval_run:1",
              agent_id: "ATLAS",
              mode: "offline",
              status: "failed",
              strategy: "offline_replay",
              summary: { total: 1, passed: 0, failed: 1, warning: 0, skipped: 0, score: 0.2 },
              cases: [
                {
                  case_key: "episode:42",
                  status: "failed",
                  score: 0.2,
                  failure_category: "policy",
                  policy_regressions: ["policy changed"],
                },
              ],
              top_failures: [{ kind: "policy", name: "policy changed", count: 1 }],
            },
          ],
        };
      }
      if (path.includes("/evals/release-quality/latest")) {
        return {
          release_quality: {
            schema_version: "release_quality.v1",
            agent_id: "ATLAS",
            status: "failing",
            gates: [
              {
                id: "smoke_eval",
                title: "Smoke eval",
                status: "failing",
                summary: "Policy regression detected.",
              },
              {
                id: "run_graph_completeness",
                title: "RunGraph completeness",
                status: "blocked",
                summary: "Missing policy_gate node.",
              },
            ],
            metrics: {
              run_graph_warnings: ["Missing policy_gate node."],
            },
            top_failures: [{ kind: "policy", name: "policy changed", count: 1 }],
          },
        };
      }
      if (path.includes("/dashboard/quality/agents/ATLAS")) {
        return {
          schema_version: "quality_cockpit.v1",
          generated_at: "2026-05-19T16:00:00Z",
          status: "degraded",
          summary: {
            success_rate: 0.72,
            failure_count: 2,
            run_count: 10,
            timeout_rate: 0.2,
            eval_trend: "regressing",
            eval_score: 0.62,
          },
          groups: [
            {
              entity_type: "agent",
              label: "Agents",
              status: "degraded",
              metrics: { success_rate: 0.72, failure_count: 2, run_count: 10, timeout_rate: 0.2 },
              items: [
                {
                  entity_type: "agent",
                  entity_id: "ATLAS",
                  label: "Atlas",
                  status: "degraded",
                  risk_class: "medium",
                  metrics: { success_rate: 0.72, failure_count: 2, run_count: 10, cost_usd: 1.2 },
                  failures: [],
                },
              ],
            },
          ],
          top_failures: [
            {
              failure_id: "quality-failure:policy",
              status: "degraded",
              risk_class: "medium",
              title: "Policy regression",
              summary: "Policy changed during eval.",
              count: 2,
              run_graph_node_ids: ["policy_gate:1"],
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
              blocker_id: "release-blocker:rungraph",
              gate_id: "run_graph_completeness",
              severity: "high",
              status: "failing",
              title: "RunGraph completeness",
              summary: "Missing policy_gate node.",
              next_action: "Inspect RunGraph completeness failures.",
              proposal_action_available: true,
            },
          ],
        };
      }
      if (path.includes("/improvement-proposals/prop%3A1/approve")) {
        return {
          schema_version: "improvement_proposal.v1",
          proposal_id: "prop:1",
          agent_id: "ATLAS",
          source_kind: "eval",
          source_ref: "eval_run:1",
          proposal_type: "tool_policy",
          summary: "Tighten policy gate",
          evidence_refs: ["eval_run:1"],
          diff_preview: { before: "allow", after: "review" },
          risk_class: "medium",
          validation_plan: { command: "offline suite" },
          rollback_plan: { effects: [{ effect_kind: "ledger_only", target_ref: "policy:1" }] },
          status: "approved",
          validation_result: {},
          run_graph_node_ids: ["node_policy"],
        };
      }
      if (path.includes("/improvement-proposals")) {
        return {
          schema_version: "improvement_proposal.v1",
          items: [
            {
              schema_version: "improvement_proposal.v1",
              proposal_id: "prop:1",
              agent_id: "ATLAS",
              source_kind: "eval",
              source_ref: "eval_run:1",
              proposal_type: "tool_policy",
              summary: "Tighten policy gate",
              evidence_refs: ["eval_run:1"],
              diff_preview: { before: "allow", after: "review" },
              risk_class: "medium",
              validation_plan: { command: "offline suite" },
              rollback_plan: { effects: [{ effect_kind: "ledger_only", target_ref: "policy:1" }] },
              status: "pending_review",
              validation_result: {},
              run_graph_node_ids: ["node_policy"],
              created_at: "2026-05-17T10:00:00Z",
              updated_at: "2026-05-17T10:00:00Z",
            },
          ],
        };
      }
      return {};
    });
  });

  it("renders a layout-matched skeleton while eval data is loading", async () => {
    requestJsonMock.mockImplementation(() => new Promise<never>(() => {}));

    renderPage();

    const skeleton = await screen.findByTestId("evaluations-page-skeleton");
    expect(within(skeleton).getByTestId("evaluations-skeleton-toolbar")).toBeInTheDocument();
    expect(within(skeleton).getAllByTestId("evaluations-skeleton-metric")).toHaveLength(6);
    expect(within(skeleton).getByTestId("evaluations-skeleton-cases-layout")).toBeInTheDocument();
    expect(skeleton.querySelectorAll("section.app-section")).toHaveLength(2);
  });

  it("renders eval cases, runs, and release health from canonical API paths", async () => {
    renderPage();

    expect(await screen.findByText("Eval cases")).toBeInTheDocument();
    expect(screen.getAllByText("Tool regression smoke").length).toBeGreaterThan(0);
    expect(screen.getByText("Release quality")).toBeInTheDocument();
    expect(screen.getByText("Case readiness")).toBeInTheDocument();
    expect(screen.getByText("1/1 cases ready")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Runs" }));
    expect(await screen.findByText("Run detail")).toBeInTheDocument();
    expect(screen.getByText("Suite health")).toBeInTheDocument();
    expect(screen.getByText("policy changed")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Release" }));
    expect(await screen.findByText("Release gates")).toBeInTheDocument();
    expect(screen.getByText("Release readiness")).toBeInTheDocument();
    expect(screen.getAllByText("Smoke eval").length).toBeGreaterThan(0);
    expect(screen.getAllByText("RunGraph completeness").length).toBeGreaterThan(0);
    expect(screen.getByText("RunGraph blocked")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Quality" }));
    await waitFor(() => expect(screen.getAllByText("Quality cockpit").length).toBeGreaterThan(0));
    expect(screen.getByText("Failure and trend evidence")).toBeInTheDocument();
    expect(screen.getByText("Policy regression")).toBeInTheDocument();
    expect(screen.getByText("Route quality trend")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Proposals" }));
    expect(await screen.findByText("Proposal queue")).toBeInTheDocument();
    expect(screen.getAllByText("Tighten policy gate").length).toBeGreaterThan(0);
    expect(screen.getByText("Proposal review")).toBeInTheDocument();

    await waitFor(() => {
      expect(requestJsonMock).toHaveBeenCalledWith(
        "/api/control-plane/agents/ATLAS/evals/cases?limit=200",
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      );
      expect(requestJsonMock).toHaveBeenCalledWith(
        "/api/control-plane/agents/ATLAS/evals/runs?limit=60",
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      );
      expect(requestJsonMock).toHaveBeenCalledWith(
        "/api/control-plane/agents/ATLAS/evals/release-quality/latest",
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      );
      expect(requestJsonMock).toHaveBeenCalledWith(
        "/api/control-plane/agents/ATLAS/improvement-proposals?limit=80",
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      );
      expect(requestJsonMock).toHaveBeenCalledWith(
        "/api/control-plane/dashboard/quality/agents/ATLAS",
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      );
    });
  });

  it("starts offline suites through the Phase 5 runs endpoint", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /Run suite/i }));

    await waitFor(() => {
      expect(requestJsonMock).toHaveBeenCalledWith(
        "/api/control-plane/agents/ATLAS/evals/runs",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("offline"),
        }),
      );
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Offline eval suite started.");
  });

  it("queues proposal actions through the canonical proposal endpoint", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("tab", { name: "Proposals" }));
    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));

    await waitFor(() => {
      expect(requestJsonMock).toHaveBeenCalledWith(
        "/api/control-plane/agents/ATLAS/improvement-proposals/prop%3A1/approve",
        expect.objectContaining({
          method: "POST",
          body: "{}",
        }),
      );
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Proposal action queued.");
  });
});
