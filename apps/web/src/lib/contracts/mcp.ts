import { z } from "zod";
import { registerBodySchema } from "@/lib/contracts/proxy-body-schemas";
import { safeText } from "@/lib/contracts/sanitizers";

/* ------------------------------------------------------------------ */
/*  Schemas                                                            */
/* ------------------------------------------------------------------ */

export const updateMcpServerBodySchema = z
  .object({
    name: safeText(240).optional(),
    command: z.string().trim().max(2000).optional(),
    args: z.array(z.string().max(500)).optional(),
    env: z.record(z.string(), z.string().max(2000)).optional(),
    enabled: z.boolean().optional(),
    url: z.string().trim().max(500).optional(),
    transport: z.enum(["stdio", "sse", "streamable-http"]).optional(),
  })
  .passthrough();

export const updateMcpPolicyBodySchema = z
  .object({
    policy: z.record(z.string(), z.string().trim().max(60)),
  })
  .passthrough();

const emptyBodySchema = z.object({}).passthrough();

/* ------------------------------------------------------------------ */
/*  Registration                                                       */
/* ------------------------------------------------------------------ */

// PUT /mcp/catalog/{serverKey}
registerBodySchema({
  method: "PUT",
  match: (s) => s.length === 3 && s[0] === "mcp" && s[1] === "catalog",
  schema: updateMcpServerBodySchema,
});

// PUT /agents/{id}/mcp/policy
registerBodySchema({
  method: "PUT",
  match: (s) =>
    s.length === 4 && s[0] === "agents" && s[2] === "mcp" && s[3] === "policy",
  schema: updateMcpPolicyBodySchema,
});

// POST /agents/{id}/mcp/discovery (no body expected)
registerBodySchema({
  method: "POST",
  match: (s) =>
    s.length === 4 &&
    s[0] === "agents" &&
    s[2] === "mcp" &&
    s[3] === "discovery",
  schema: emptyBodySchema,
});
