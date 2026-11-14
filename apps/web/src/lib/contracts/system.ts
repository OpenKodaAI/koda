import { z } from "zod";
import { registerBodySchema } from "@/lib/contracts/proxy-body-schemas";

/*  Schemas                                                            */

export const patchGlobalDefaultsBodySchema = z.object({
  sections: z.record(z.string(), z.record(z.string(), z.unknown())),
});

// GET /system-settings/placeholder-secrets: `.env` key names whose values are
// still `.env.example` placeholders. The route never returns values.
export const placeholderSecretsStatusSchema = z.object({
  placeholder_keys: z.array(z.string().regex(/^[A-Z][A-Z0-9_]{0,63}$/)).max(16),
  rotation_url: z
    .string()
    .trim()
    .url()
    .max(500)
    .refine((value) => value.startsWith("https://"), "rotation_url must use https"),
});

export type PlaceholderSecretsStatus = z.infer<typeof placeholderSecretsStatusSchema>;

/*  Registration                                                       */

// PATCH /global-defaults
registerBodySchema({
  method: "PATCH",
  match: (s) => s.length === 1 && s[0] === "global-defaults",
  schema: patchGlobalDefaultsBodySchema,
});
