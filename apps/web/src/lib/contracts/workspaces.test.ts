import { describe, expect, it } from "vitest";

import "@/lib/contracts/workspaces";
import {
  workspaceBodySchema,
  workspaceDirectoryEntrySchema,
  workspaceDirectoryBodySchema,
  workspaceDirectoryRootSchema,
  workspaceImportBodySchema,
  workspaceImportConfigBodySchema,
  workspaceImportResultSchema,
  workspaceScanPayloadSchema,
} from "@/lib/contracts/workspaces";
import { resolveBodySchema } from "@/lib/contracts/proxy-body-schemas";

describe("workspace proxy body schemas", () => {
  it("accepts workspace roots and scan-on-save flags", () => {
    expect(
      workspaceBodySchema.parse({
        name: "  Produto  ",
        description: "  Imports locais  ",
        root_path: " /workspace/project ",
        scan_on_save: true,
      }),
    ).toEqual({
      name: "Produto",
      description: "Imports locais",
      root_path: "/workspace/project",
      scan_on_save: true,
    });
  });

  it("registers fixed workspace directory routes before dynamic workspace routes", () => {
    expect(resolveBodySchema("POST", ["workspaces", "list-directory"])).toBe(
      workspaceDirectoryBodySchema,
    );
    expect(resolveBodySchema("POST", ["workspaces", "scan-directory"])).toBe(
      workspaceDirectoryBodySchema,
    );
    expect(resolveBodySchema("POST", ["workspaces", "import"])).toBe(
      workspaceImportBodySchema,
    );
    expect(resolveBodySchema("POST", ["workspaces", "workspace-product", "rescan"])).toBe(
      workspaceImportConfigBodySchema,
    );
    expect(
      resolveBodySchema("POST", ["workspaces", "workspace-product", "import-config"]),
    ).toBe(workspaceImportConfigBodySchema);
  });

  it("rejects unsafe or malformed import payloads", () => {
    expect(() => workspaceDirectoryBodySchema.parse({ path: "", maxDepth: 0 })).toThrow();
    expect(() =>
      workspaceImportBodySchema.parse({
        path: "/repo",
        selectedSourceIds: ["A".repeat(300)],
      }),
    ).toThrow();
  });

  it("accepts directory and scan response payloads", () => {
    expect(workspaceDirectoryRootSchema.parse({ path: "/repo", label: "repo" })).toEqual({
      path: "/repo",
      label: "repo",
    });
    expect(workspaceDirectoryEntrySchema.parse({ path: "/repo/src", name: "src", kind: "directory" })).toEqual({
      path: "/repo/src",
      name: "src",
      kind: "directory",
    });
    expect(
      workspaceScanPayloadSchema.parse({
        schema_version: "workspace_config_scan.v1",
        root_path: "/repo",
        root_kind: "local_path",
        scan_hash: "abc",
        status: "completed",
        summary: {
          total_sources: 1,
          by_tool: { codex: 1 },
          by_kind: { instructions: 1 },
          by_risk: { low: 1 },
          importable: 1,
          review_required: 0,
          blocked: 0,
          truncated: false,
        },
        sources: [
          {
            source_id: "src1",
            tool: "codex",
            kind: "instructions",
            relative_path: "AGENTS.md",
            risk: "low",
            import_action: "append_workspace_prompt",
            warnings: [],
            metadata: {},
            content_excerpt: "Use tests.",
          },
        ],
        warnings: [],
      }),
    ).toMatchObject({ scan_hash: "abc", summary: { importable: 1 } });
    expect(workspaceImportResultSchema.parse({ applied: [], skipped: [], conflicts: [] })).toEqual({
      applied: [],
      skipped: [],
      conflicts: [],
    });
  });
});
