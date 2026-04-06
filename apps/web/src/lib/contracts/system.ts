import { z } from "zod";
import { registerBodySchema } from "@/lib/contracts/proxy-body-schemas";

/* ------------------------------------------------------------------ */
/*  Schemas                                                            */
/* ------------------------------------------------------------------ */

export const patchGlobalDefaultsBodySchema = z.object({
  sections: z.record(z.string(), z.record(z.string(), z.unknown())),
});

/* ------------------------------------------------------------------ */
/*  Registration                                                       */
/* ------------------------------------------------------------------ */

// PATCH /global-defaults
registerBodySchema({
  method: "PATCH",
  match: (s) => s.length === 1 && s[0] === "global-defaults",
  schema: patchGlobalDefaultsBodySchema,
});
