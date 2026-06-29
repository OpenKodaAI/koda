import { z } from "zod";
import { registerBodySchema } from "@/lib/contracts/proxy-body-schemas";

const CONTROL_CHAR_PATTERN = /[\x00-\x1f\x7f]/;

export const updateOperatorProfileBodySchema = z
  .object({
    display_name: z
      .string()
      .max(200)
      .superRefine((value, ctx) => {
        if (CONTROL_CHAR_PATTERN.test(value)) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: "Display name cannot contain control characters.",
          });
        }
      })
      .transform((value) => value.trim().split(/\s+/).filter(Boolean).join(" "))
      .pipe(z.string().min(1, "Display name is required.").max(80, "Display name must be 80 characters or fewer.")),
  })
  .strict();

registerBodySchema({
  method: "PATCH",
  match: (segments) => segments.length === 2 && segments[0] === "auth" && segments[1] === "profile",
  schema: updateOperatorProfileBodySchema,
});
