import { describe, expect, it } from "vitest";
import {
  evalErrorMessage,
  parseEvalCases,
  parseEvalRun,
  parseEvalRuns,
  parseReleaseQuality,
  parseTrajectoryExport,
} from "@/lib/contracts/evals";

describe("Phase 5 eval contracts", () => {
  it("parses eval_case.v1 payloads and keeps backend expectations opaque", () => {
    const cases = parseEvalCases({
      items: [
        {
          schema_version: "eval_case.v1",
          case_key: "episode:42",
          agent_id: "ATLAS",
          title: "<script>alert(1)</script> Tool regression",
          status: "ready",
          source: "run",
          source_task_id: 42,
          run_id: "run:42",
          input_preview: "Summarize the incident.",
          expected_output_preview: "A grounded summary.",
          expected_sources: ["runbook:incident"],
          expected_layers: ["canonical"],
          tool_expectations: [{ tool_id: "read_file" }],
          policy_expectations: [{ decision: "allow" }],
          tags: ["smoke"],
          metadata: { owner: "qa" },
        },
      ],
    });

    expect(cases).toHaveLength(1);
    expect(cases[0]?.schema_version).toBe("eval_case.v1");
    expect(cases[0]?.title).toBe(" Tool regression");
    expect(cases[0]?.tool_expectations[0]?.tool_id).toBe("read_file");
  });

  it("normalizes legacy knowledge eval rows for compatibility", () => {
    const cases = parseEvalCases([
      {
        case_key: "runbook:7",
        agent_id: "ATLAS",
        query_text: "What is the deploy rollback?",
        reference_answer: "Use the rollback runbook.",
        status: "draft",
        expected_sources_json: ["runbook:rollback"],
        expected_layers_json: ["runbook"],
        metadata_json: { tags: ["legacy"] },
      },
    ]);

    expect(cases[0]?.schema_version).toBe("eval_case.v1");
    expect(cases[0]?.input_preview).toBe("What is the deploy rollback?");
    expect(cases[0]?.expected_output_preview).toBe("Use the rollback runbook.");
    expect(cases[0]?.tags).toContain("legacy");
  });

  it("parses eval_run.v1 and legacy run rows", () => {
    const canonical = parseEvalRun({
      run: {
        schema_version: "eval_run.v1",
        run_id: "eval_run:1",
        agent_id: "ATLAS",
        mode: "offline",
        status: "failed",
        strategy: "offline_replay",
        summary: { total: 2, passed: 1, failed: 1, warning: 0, skipped: 0, score: 0.5 },
        cases: [
          {
            case_key: "episode:42",
            status: "failed",
            score: 0.2,
            failure_category: "policy",
            policy_regressions: ["policy gate changed"],
          },
        ],
        top_failures: [{ kind: "policy", name: "policy gate changed", count: 1 }],
      },
    });
    const legacy = parseEvalRuns({
      items: [
        {
          id: 9,
          case_key: "episode:42",
          agent_id: "ATLAS",
          strategy: "knowledge",
          task_success_proxy: 0.91,
          metrics_json: { citation_accuracy: 0.88 },
        },
      ],
    });

    expect(canonical?.status).toBe("failed");
    expect(canonical?.cases[0]?.policy_regressions).toContain("policy gate changed");
    expect(legacy[0]?.run_id).toBe("eval_run:9");
    expect(legacy[0]?.status).toBe("passed");
  });

  it("parses trajectory_export.v1 and release_quality.v1 payloads", () => {
    const trajectory = parseTrajectoryExport({
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
        line_count: 12,
        redactions: { count: 2, fields: ["prompt", "env"] },
      },
    });
    const release = parseReleaseQuality({
      release_quality: {
        schema_version: "release_quality.v1",
        agent_id: "ATLAS",
        status: "passing",
        gates: [
          {
            id: "smoke_eval",
            title: "Smoke eval",
            status: "passing",
            summary: "All deterministic checks passed.",
          },
        ],
        top_failures: [],
      },
    });

    expect(trajectory?.format).toBe("jsonl");
    expect(trajectory?.provider_calls_disabled).toBe(true);
    expect(release?.status).toBe("passing");
    expect(release?.gates[0]?.id).toBe("smoke_eval");
  });

  it("normalizes backend-shaped release quality gates and failure groups", () => {
    const release = parseReleaseQuality({
      release_quality: {
        schema_version: "release_quality.v1",
        agent_id: "ATLAS",
        status: "passed",
        gates: {
          offline_eval: { status: "passed", threshold: 0.8 },
          browser_authenticated_e2e: {
            status: "blocked",
            message: "Authenticated browser E2E depends on local Browser/auth infrastructure.",
          },
        },
        failure_groups: [{ category: "policy_regression", count: 2 }],
      },
    });

    expect(release?.status).toBe("passed");
    expect(release?.gates.map((gate) => gate.id)).toContain("offline_eval");
    expect(release?.gates.find((gate) => gate.id === "browser_authenticated_e2e")?.status).toBe("blocked");
    expect(release?.top_failures[0]?.kind).toBe("policy");
    expect(release?.top_failures[0]?.name).toBe("policy_regression");
  });

  it("extracts operational error envelope messages", () => {
    expect(
      evalErrorMessage({
        error: {
          code: "eval.replay_unavailable",
          category: "dependency_unavailable",
          message: "Offline replay is unavailable.",
          retryable: false,
          user_action: "Create a new case from a task with RunGraph data.",
        },
      }),
    ).toContain("Create a new case");
    expect(evalErrorMessage(new Error("[object Object]"), "Fallback message")).toBe("Fallback message");
  });
});
