import { z } from "zod";
import { safeText } from "@/lib/contracts/sanitizers";

/* ------------------------------------------------------------------ */
/*  Slash-command catalog contracts                                    */
/*  GET /api/control-plane/commands/list -> { items: ChatCommand[] }   */
/* ------------------------------------------------------------------ */

const chatCommandActionInsert = z.object({
  kind: z.literal("insert"),
  /** Text appended to the textarea (e.g. "/new-session "). */
  template: z.string().trim().min(1).max(240),
});

const chatCommandActionExecute = z.object({
  kind: z.literal("execute"),
  /** Discriminator handled by sessions-page-client.tsx commandRouter. */
  type: z.enum([
    "new-session",
    "clear-thread",
    "open-context",
    "switch-agent",
    "rename-session",
    "summarize",
  ]),
  payload: z.record(z.string(), z.unknown()).optional(),
});

const chatCommandActionRemote = z.object({
  kind: z.literal("remote"),
  /** Endpoint relative to control-plane (e.g. "agents/.../macro"). */
  endpoint: z.string().trim().min(1).max(240),
  payload: z.record(z.string(), z.unknown()).optional(),
});

export const chatCommandActionSchema = z.discriminatedUnion("kind", [
  chatCommandActionInsert,
  chatCommandActionExecute,
  chatCommandActionRemote,
]);

export type ChatCommandAction = z.infer<typeof chatCommandActionSchema>;

export const chatCommandSchema = z.object({
  id: z.string().trim().min(1).max(64).regex(/^[a-z0-9_\-]+$/),
  /** Visible in the popover (e.g. "/new-session"). */
  label: safeText(48),
  description: safeText(200),
  /** Lucide icon name (e.g. "MessagesSquare") OR a URL/path to an SVG. */
  icon: z.string().trim().max(2000).nullable().optional(),
  /** When set, command only appears for these agent ids. Empty = global. */
  agent_scope: z.array(z.string().trim().max(120)).max(32).optional(),
  /** When set, command only appears when matching keywords in the query. */
  keywords: z.array(z.string().trim().max(48)).max(16).optional(),
  action: chatCommandActionSchema,
});

export type ChatCommand = z.infer<typeof chatCommandSchema>;

export const chatCommandsCatalogSchema = z.object({
  items: z.array(chatCommandSchema).max(64),
});

export type ChatCommandsCatalog = z.infer<typeof chatCommandsCatalogSchema>;

/* ------------------------------------------------------------------ */
/*  Skill-search contracts                                             */
/*  GET /api/control-plane/skills/search?q=...                         */
/*       -> { items: SkillSuggestion[] }                               */
/* ------------------------------------------------------------------ */

export const skillSuggestionSchema = z.object({
  slug: z
    .string()
    .trim()
    .min(1)
    .max(64)
    .regex(/^[a-z0-9_\-]+$/, "Skill slugs are lowercase alphanumeric with _ or -."),
  label: safeText(120),
  description: safeText(280).nullable().optional(),
  /** Hex colour (#RRGGBB) for the badge; null falls back to neutral. */
  color: z
    .string()
    .trim()
    .regex(/^#[0-9a-fA-F]{6}$/)
    .nullable()
    .optional(),
  icon: z.string().trim().max(2000).nullable().optional(),
});

export type SkillSuggestion = z.infer<typeof skillSuggestionSchema>;

export const skillSearchResponseSchema = z.object({
  items: z.array(skillSuggestionSchema).max(32),
});

export type SkillSearchResponse = z.infer<typeof skillSearchResponseSchema>;

/* ------------------------------------------------------------------ */
/*  Static fallback catalog                                            */
/*  Used when the commands endpoint is unreachable; ALSO acts as the   */
/*  contract for what shipped client-side (always available).          */
/* ------------------------------------------------------------------ */

export const STATIC_COMMAND_FALLBACK: ChatCommand[] = [
  {
    id: "new-session",
    label: "/new-session",
    description: "Start a fresh chat with the current agent.",
    icon: "MessageCirclePlus",
    action: { kind: "execute", type: "new-session" },
  },
  {
    id: "clear-thread",
    label: "/clear",
    description: "Hide the current thread from view (does not delete).",
    icon: "Eraser",
    action: { kind: "execute", type: "clear-thread" },
  },
  {
    id: "open-context",
    label: "/context",
    description: "Open the session context drawer.",
    icon: "PanelRight",
    action: { kind: "execute", type: "open-context" },
  },
  {
    id: "summarize",
    label: "/summarize",
    description: "Ask the agent to summarize the conversation so far.",
    icon: "Sparkles",
    action: { kind: "execute", type: "summarize" },
  },
];
