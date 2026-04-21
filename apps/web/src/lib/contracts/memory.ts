import { z } from "zod";
import { registerBodySchema } from "@/lib/contracts/proxy-body-schemas";

/* ------------------------------------------------------------------ */
/*  Schemas                                                            */
/* ------------------------------------------------------------------ */

export const memoryCurationActionBodySchema = z.object({
  target_type: z.enum(["memory", "cluster"]),
  target_ids: z.array(z.string().trim().min(1).max(240)).min(1),
  action: z.string().trim().min(1).max(60),
  duplicate_of_memory_id: z.number().int().nullable().optional(),
});

/* ------------------------------------------------------------------ */
/*  Registration                                                       */
/* ------------------------------------------------------------------ */

// POST /agents/{id}/memory-curation/actions
registerBodySchema({
  method: "POST",
  match: (s) =>
    s.length === 4 &&
    s[0] === "agents" &&
    s[2] === "memory-curation" &&
    s[3] === "actions",
  schema: memoryCurationActionBodySchema,
});
