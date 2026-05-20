import { describe, expect, it } from "vitest";
import {
  improvementProposalActionBodySchema,
  parseImprovementProposal,
  parseImprovementProposals,
} from "@/lib/contracts/improvement-proposals";
import { resolveBodySchema } from "@/lib/contracts/proxy-body-schemas";

describe("improvement proposal contracts", () => {
  it("parses canonical proposal lists", () => {
    const proposals = parseImprovementProposals({
      schema_version: "improvement_proposal.v1",
      items: [
        {
          schema_version: "improvement_proposal.v1",
          proposal_id: "prop:1",
          agent_id: "ATLAS",
          source_kind: "eval",
          source_ref: "eval_run:1",
          proposal_type: "prompt",
          summary: "Clarify escalation prompt",
          evidence_refs: [{ kind: "eval_run", id: "eval_run:1" }],
          diff_preview: { before: "old", after: "new" },
          risk_class: "medium",
          validation_plan: { suite_id: "default" },
          validation_result: { status: "passed" },
          rollback_plan: { restore_snapshot: "prompt:v1" },
          status: "pending_review",
          run_graph_node_ids: ["node_policy"],
        },
      ],
    });

    expect(proposals).toHaveLength(1);
    expect(proposals[0]).toMatchObject({
      schema_version: "improvement_proposal.v1",
      proposal_id: "prop:1",
      source_kind: "eval",
      proposal_type: "prompt",
      status: "pending_review",
    });
    expect(proposals[0].diff_preview).toMatchObject({ after: "new" });
    expect(proposals[0].validation_result.status).toBe("passed");
  });

  it("parses raw single proposal payloads without legacy wrappers", () => {
    const proposal = parseImprovementProposal({
      schema_version: "improvement_proposal.v1",
      proposal_id: "proposal-2",
      source_kind: "manual",
      source_ref: "operator:1",
      proposal_type: "tool_policy",
      summary: "Add review gate",
      evidence_refs: [{ kind: "manual", id: "operator:1" }],
      diff_preview: { after: "review" },
      risk_class: "high",
      validation_plan: { mode: "offline" },
      rollback_plan: { effects: [] },
      status: "pending_review",
      run_graph_node_ids: ["runtime_event:1"],
    });

    expect(proposal).toMatchObject({
      schema_version: "improvement_proposal.v1",
      proposal_id: "proposal-2",
      source_kind: "manual",
      proposal_type: "tool_policy",
      risk_class: "high",
      status: "pending_review",
    });
  });

  it("rejects invalid risk instead of reclassifying it", () => {
    const proposal = parseImprovementProposal({
      schema_version: "improvement_proposal.v1",
      proposal_id: "proposal-3",
      source_kind: "manual",
      source_ref: "operator:1",
      proposal_type: "tool_policy",
      summary: "Add review gate",
      evidence_refs: [{ kind: "manual", id: "operator:1" }],
      diff_preview: { after: "review" },
      risk_class: "unknown",
      validation_plan: { mode: "offline" },
      rollback_plan: { effects: [] },
      status: "pending_review",
      run_graph_node_ids: ["runtime_event:1"],
    });

    expect(proposal).toBeNull();
  });

  it("registers action body validation for the control-plane proxy", () => {
    const schema = resolveBodySchema("POST", [
      "agents",
      "ATLAS",
      "improvement-proposals",
      "prop:1",
      "approve",
    ]);

    expect(schema).toBe(improvementProposalActionBodySchema);
    expect(schema?.parse({ note: "Looks safe.", validation_result: { status: "passed" } })).toMatchObject({
      note: "Looks safe.",
      validation_result: { status: "passed" },
    });
  });
});
