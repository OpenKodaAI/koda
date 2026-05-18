import { describe, expect, it } from "vitest";
import {
  parseSkillPackageError,
  parseSkillPackageLocks,
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
          rollback_ref: null,
        },
      ],
    });

    expect(locks).toHaveLength(1);
    expect(locks[0]?.installed_tools[0]?.id).toBe("safe_notes");
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
