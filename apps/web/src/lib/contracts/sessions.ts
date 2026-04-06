import { z } from "zod";
import { registerBodySchema } from "@/lib/contracts/proxy-body-schemas";
import { safeContent } from "@/lib/contracts/sanitizers";

/* ------------------------------------------------------------------ */
/*  Schemas                                                            */
/* ------------------------------------------------------------------ */

export const sendSessionMessageBodySchema = z.object({
  text: safeContent(10_000).min(1, "Message text is required."),
  session_id: z.string().trim().max(240).nullable().optional(),
});

/* ------------------------------------------------------------------ */
/*  Registration (dashboard proxy: /agents/{id}/sessions/messages)     */
/* ------------------------------------------------------------------ */

registerBodySchema({
  method: "POST",
  match: (s) =>
    s.length === 4 &&
    s[0] === "agents" &&
    s[2] === "sessions" &&
    s[3] === "messages",
  schema: sendSessionMessageBodySchema,
});
