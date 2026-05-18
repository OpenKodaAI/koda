import { describe, expect, it } from "vitest";

import "@/lib/contracts/workspaces";
import {
  workspaceBodySchema,
  workspaceDirectoryBodySchema,
  workspaceImportBodySchema,
  workspaceImportConfigBodySchema,
} from "@/lib/contracts/workspaces";
import { resolveBodySchema } from "@/lib/contracts/proxy-body-schemas";

describe("workspace proxy body schemas", () => {
  it("accepts workspace roots and scan-on-save flags", () => {
    expect(
      workspaceBodySchema.parse({
        name: "  Produto  ",
        description: "  Imports locais  ",
        root_path: " /Users/me/project ",
        scan_on_save: true,
      }),
    ).toEqual({
      name: "Produto",
      description: "Imports locais",
      root_path: "/Users/me/project",
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
});
