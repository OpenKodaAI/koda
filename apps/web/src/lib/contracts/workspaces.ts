import { z } from "zod";
import { registerBodySchema } from "@/lib/contracts/proxy-body-schemas";
import { hexColor, safeContent, safeText } from "@/lib/contracts/sanitizers";

/* ------------------------------------------------------------------ */
/*  Schemas                                                            */
/* ------------------------------------------------------------------ */

export const workspaceBodySchema = z.object({
  name: safeText(240),
  description: safeText(2000).optional().default(""),
  color: hexColor(),
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

/* ------------------------------------------------------------------ */
/*  Registration                                                       */
/* ------------------------------------------------------------------ */

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
