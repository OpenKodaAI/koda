import { describe, expect, it } from "vitest";
import {
  parseSkillPackageError,
  parseSkillPackageLocks,
  parseSkillRegistry,
  parseSkillScanResult,
  skillPackageErrorMessage,
} from "@/lib/contracts/skill-package";

describe("skill package contracts", () => {
  it("parses skill_scan.v1 payloads", () => {
    const scan = parseSkillScanResult({
      ok: true,
      scan: {
        schema_version: "skill_scan.v1",
        decision: "review_required",
        severity: "warning",
        findings: [
          {
            id: "permission.network",
            severity: "warning",
            category: "permissions",
            message: "Network permission requires operator review.",
            path: "/tmp/pkg/koda-skill.yaml",
            user_action: "Review the package before installing.",
          },
        ],
        permissions_requested: { network: true },
        risk_classes: ["network_write"],
        redactions: [],
        package_hash: "abc123",
        file_hashes: { "koda-skill.yaml": "hash" },
        scanner_version: "skill_package_scanner.v1",
        package: {
          schema_version: "koda_skill.v1",
          id: "safe_pack",
          name: "Safe Pack",
          version: "1.0.0",
          description: "Safe local package.",
          author: "Koda Tests",
          permissions: { network: true },
          docs: {},
          skills: [{ id: "safe_review" }],
          tools: [{ id: "safe_notes" }],
        },
      },
    });

    expect(scan?.decision).toBe("review_required");
    expect(scan?.findings[0]?.id).toBe("permission.network");
    expect(scan?.package.tools).toHaveLength(1);
  });

  it("parses skill_lock.v1 payloads", () => {
    const locks = parseSkillPackageLocks({
      items: [
        {
          schema_version: "skill_lock.v1",
          package_id: "safe_pack",
          name: "Safe Pack",
          version: "1.0.0",
          package_hash: "abc123",
          agent_id: "ATLAS",
          installed_skills: [{ id: "safe_review" }],
          installed_tools: [{ id: "safe_notes" }],
          scan_summary: {},
          skill_evals: [{ eval_id: "safe_review.eval", result: { status: "passed" } }],
          recommendation_status: "unreviewed",
          eval_summary: { passed: 1, failed: 0 },
          trust_summary: { source: "local", score: 0.92 },
          rollback_ref: null,
        },
      ],
    });

    expect(locks).toHaveLength(1);
    expect(locks[0]?.installed_tools[0]?.id).toBe("safe_notes");
    expect(locks[0]?.recommendation_status).toBe("unreviewed");
    expect(locks[0]?.skill_evals[0]?.eval_id).toBe("safe_review.eval");
    expect(locks[0]?.eval_summary.passed).toBe(1);
    expect(locks[0]?.trust_summary.score).toBe(0.92);
  });

  it("rejects invalid recommendation statuses", () => {
    const locks = parseSkillPackageLocks({
      items: [
        {
          schema_version: "skill_lock.v1",
          package_id: "safe_pack",
          name: "Safe Pack",
          version: "1.0.0",
          package_hash: "abc123",
          agent_id: "ATLAS",
          installed_skills: [],
          installed_tools: [],
          scan_summary: {},
          recommendation_status: "safe_enough",
        },
      ],
    });

    expect(locks).toEqual([]);
  });

  it("parses skill_registry.v1 payloads", () => {
    const registry = parseSkillRegistry({
      schema_version: "skill_registry.v1",
      agent_id: "ATLAS",
      items: [
        {
          schema_version: "skill_registry.v1",
          agent_id: "ATLAS",
          package_id: "safe_pack",
          name: "Safe Pack",
          version: "1.0.0",
          package_hash: "abc123",
          installed: true,
          recommendation_status: "recommended",
          scan_summary: { decision: "allow" },
          eval_summary: { required_passed_all: true },
          trust_summary: { recommended: true },
          skills: [{ id: "safe_review" }],
          tools: [{ id: "safe_notes" }],
          rollback_available: true,
          run_graph_evidence: { node_type: "runtime_event" },
        },
      ],
    });

    expect(registry.items[0]?.package_id).toBe("safe_pack");
    expect(registry.items[0]?.recommendation_status).toBe("recommended");
    expect(registry.items[0]?.run_graph_evidence.node_type).toBe("runtime_event");
  });

  it("extracts structured error envelope messages", () => {
    const payload = {
      ok: false,
      error: {
        code: "skill.scan_denied",
        category: "policy_denied",
        message: "Skill package scan denied installation.",
        retryable: false,
        user_action: "Resolve scanner findings before installing.",
      },
    };

    expect(parseSkillPackageError(payload)?.code).toBe("skill.scan_denied");
    expect(skillPackageErrorMessage(payload)).toContain("Resolve scanner findings");
  });
});
