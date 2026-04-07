import { z } from "zod";
import { registerBodySchema } from "@/lib/contracts/proxy-body-schemas";
import {
  hexColor,
  rgbString,
  safeContent,
  safeIdentifier,
  safeText,
} from "@/lib/contracts/sanitizers";

/* ------------------------------------------------------------------ */
/*  Schemas                                                            */
/* ------------------------------------------------------------------ */

export const createAgentBodySchema = z.object({
  id: safeIdentifier(120),
  display_name: safeText(240),
  status: z.enum(["active", "paused"]).default("paused"),
  storage_namespace: safeIdentifier(120),
  appearance: z.object({
    label: safeText(240),
    color: hexColor(),
    color_rgb: rgbString(),
  }),
  runtime_endpoint: z
    .object({
      health_port: z.number().int().min(1).max(65535),
      health_url: z.string().trim().max(500),
      runtime_base_url: z.string().trim().max(500),
    })
    .passthrough(),
}).passthrough();

export const patchAgentBodySchema = z.object({
  organization: z
    .object({
      workspace_id: z.string().trim().max(120).nullable(),
      squad_id: z.string().trim().max(120).nullable(),
    })
    .optional(),
}).passthrough();

export const cloneAgentBodySchema = z.object({
  id: safeIdentifier(120),
  display_name: safeText(240),
});

export const updateDocumentBodySchema = z.object({
  content: safeContent(100_000),
});

export const updateAgentSpecBodySchema = z.object({
  model_policy: z
    .object({
      allowed_providers: z.array(z.string().trim().max(60)).optional(),
      default_provider: z.string().trim().max(60).optional(),
      fallback_order: z.array(z.string().trim().max(60)).optional(),
      available_models_by_provider: z.record(z.string(), z.array(z.string())).optional(),
      default_models: z.record(z.string(), z.string()).optional(),
      tier_models: z.record(z.string(), z.record(z.string(), z.string())).optional(),
    })
    .passthrough()
    .optional(),
}).passthrough();

const emptyBodySchema = z.object({}).passthrough();

export const updateScopeBodySchema = z.object({}).passthrough();

export const onboardingBootstrapBodySchema = z.object({
  account: z.object({
    owner_name: safeText(240),
    owner_email: z.string().trim().email().max(320),
    owner_github: safeText(240).optional().default(""),
  }),
  access: z.object({
    allowed_user_ids: z.string().trim().max(2000),
  }),
  provider: z.object({
    provider_id: safeIdentifier(60),
    auth_mode: z.enum(["api_key", "local"]),
    api_key: z.string().trim().max(500).optional().default(""),
    project_id: z.string().trim().max(240).optional().default(""),
    base_url: z.string().trim().max(500).optional().default(""),
  }),
  agent: z
    .object({
      agent_id: safeIdentifier(120).optional(),
      display_name: safeText(240).optional(),
      telegram_token: z.string().trim().max(500).optional(),
    })
    .passthrough()
    .optional()
    .default({}),
}).passthrough();

/* ------------------------------------------------------------------ */
/*  Registration                                                       */
/* ------------------------------------------------------------------ */

// POST /agents
registerBodySchema({
  method: "POST",
  match: (s) => s.length === 1 && s[0] === "agents",
  schema: createAgentBodySchema,
});

// PATCH /agents/{id}
registerBodySchema({
  method: "PATCH",
  match: (s) => s.length === 2 && s[0] === "agents",
  schema: patchAgentBodySchema,
});

// POST /agents/{id}/clone
registerBodySchema({
  method: "POST",
  match: (s) => s.length === 3 && s[0] === "agents" && s[2] === "clone",
  schema: cloneAgentBodySchema,
});

// PUT /agents/{id}/documents/{docId}
registerBodySchema({
  method: "PUT",
  match: (s) => s.length === 4 && s[0] === "agents" && s[2] === "documents",
  schema: updateDocumentBodySchema,
});

// PUT /agents/{id}/agent-spec
registerBodySchema({
  method: "PUT",
  match: (s) => s.length === 3 && s[0] === "agents" && s[2] === "agent-spec",
  schema: updateAgentSpecBodySchema,
});

// POST /agents/{id}/publish, /agents/{id}/activate, /agents/{id}/pause
for (const action of ["publish", "activate", "pause"]) {
  registerBodySchema({
    method: "POST",
    match: (s) => s.length === 3 && s[0] === "agents" && s[2] === action,
    schema: emptyBodySchema,
  });
}

// PUT /agents/{id}/scopes/{scopeId}
registerBodySchema({
  method: "PUT",
  match: (s) => s.length === 4 && s[0] === "agents" && s[2] === "scopes",
  schema: updateScopeBodySchema,
});

// POST /agents/{id}/scopes
registerBodySchema({
  method: "POST",
  match: (s) => s.length === 3 && s[0] === "agents" && s[2] === "scopes",
  schema: updateScopeBodySchema,
});

// POST /onboarding/bootstrap
registerBodySchema({
  method: "POST",
  match: (s) => s.length === 2 && s[0] === "onboarding" && s[1] === "bootstrap",
  schema: onboardingBootstrapBodySchema,
});
