import { z } from "zod";
import { registerBodySchema } from "@/lib/contracts/proxy-body-schemas";
import { hexColor, safeContent, safeText } from "@/lib/contracts/sanitizers";

/*  Schemas                                                            */

export const workspaceBodySchema = z.object({
  name: safeText(240),
  description: safeText(2000).optional().default(""),
  color: hexColor().optional(),
  root_path: safeText(4000).nullable().optional(),
  scan_on_save: z.boolean().optional(),
});

export const squadBodySchema = z.object({
  name: safeText(240),
  description: safeText(2000).optional().default(""),
  color: hexColor(),
});

export const workspaceSpecBodySchema = z.object({
  spec: z.record(z.string(), z.unknown()).optional(),
  documents: z
    .object({
      system_prompt_md: safeContent(100_000).optional(),
    })
    .optional(),
}).passthrough();

export const workspaceDirectoryBodySchema = z.object({
  path: safeText(4000),
  maxDepth: z.number().int().min(1).max(24).optional(),
  max_depth: z.number().int().min(1).max(24).optional(),
});

export const workspaceImportBodySchema = workspaceDirectoryBodySchema.extend({
  name: safeText(240).optional(),
  description: safeText(2000).optional(),
  selectedSourceIds: z.array(safeText(256)).optional(),
  selected_source_ids: z.array(safeText(256)).optional(),
});

export const workspaceImportConfigBodySchema = z.object({
  selectedSourceIds: z.array(safeText(256)).optional(),
  selected_source_ids: z.array(safeText(256)).optional(),
  rescan: z.boolean().optional(),
  maxDepth: z.number().int().min(1).max(24).optional(),
  max_depth: z.number().int().min(1).max(24).optional(),
});

/*  Registration                                                       */

// POST /workspaces
registerBodySchema({
  method: "POST",
  match: (s) => s.length === 1 && s[0] === "workspaces",
  schema: workspaceBodySchema,
});

// PATCH /workspaces/{id}
registerBodySchema({
  method: "PATCH",
  match: (s) => s.length === 2 && s[0] === "workspaces",
  schema: workspaceBodySchema,
});

// POST /workspaces/list-directory
registerBodySchema({
  method: "POST",
  match: (s) => s.length === 2 && s[0] === "workspaces" && s[1] === "list-directory",
  schema: workspaceDirectoryBodySchema,
});

// POST /workspaces/scan-directory
registerBodySchema({
  method: "POST",
  match: (s) => s.length === 2 && s[0] === "workspaces" && s[1] === "scan-directory",
  schema: workspaceDirectoryBodySchema,
});

// POST /workspaces/import
registerBodySchema({
  method: "POST",
  match: (s) => s.length === 2 && s[0] === "workspaces" && s[1] === "import",
  schema: workspaceImportBodySchema,
});

// POST /workspaces/{id}/rescan
registerBodySchema({
  method: "POST",
  match: (s) => s.length === 3 && s[0] === "workspaces" && s[2] === "rescan",
  schema: workspaceImportConfigBodySchema,
});

// POST /workspaces/{id}/import-config
registerBodySchema({
  method: "POST",
  match: (s) => s.length === 3 && s[0] === "workspaces" && s[2] === "import-config",
  schema: workspaceImportConfigBodySchema,
});

// POST /workspaces/{id}/squads
registerBodySchema({
  method: "POST",
  match: (s) => s.length === 3 && s[0] === "workspaces" && s[2] === "squads",
  schema: squadBodySchema,
});

// PATCH /workspaces/{id}/squads/{squadId}
registerBodySchema({
  method: "PATCH",
  match: (s) => s.length === 4 && s[0] === "workspaces" && s[2] === "squads",
  schema: squadBodySchema,
});

// PUT /workspaces/{id}/spec
registerBodySchema({
  method: "PUT",
  match: (s) => s.length === 3 && s[0] === "workspaces" && s[2] === "spec",
  schema: workspaceSpecBodySchema,
});

// PUT /workspaces/{id}/squads/{squadId}/spec
registerBodySchema({
  method: "PUT",
  match: (s) =>
    s.length === 5 &&
    s[0] === "workspaces" &&
    s[2] === "squads" &&
    s[4] === "spec",
  schema: workspaceSpecBodySchema,
});
