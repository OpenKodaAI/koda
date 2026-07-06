import { z } from "zod";
import { operationalErrorEnvelopeSchema } from "@/lib/contracts/run-graph";
import { registerBodySchema } from "@/lib/contracts/proxy-body-schemas";
import { safeContent, safeIdentifier, safeText } from "@/lib/contracts/sanitizers";

export const channelGatewayStatusSchema = z.enum([
  "pending",
  "paired",
  "allowed",
  "blocked",
  "revoked",
]);

export const channelGatewayIdentitySchema = z
  .object({
    schema_version: z.literal("channel_gateway.v1").default("channel_gateway.v1"),
    identity_id: safeIdentifier(120),
    agent_id: safeIdentifier(120),
    channel_type: safeIdentifier(80),
    channel_id: safeText(240),
    user_id: safeText(240),
    display_name: safeText(240),
    is_group: z.boolean().default(false),
    status: channelGatewayStatusSchema,
    scopes: z.array(safeIdentifier(80)).max(40).default(["message"]),
    source: safeText(120).default("channel_gateway"),
    allowed_by: safeText(240).default(""),
    blocked_by: safeText(240).default(""),
    revoked_by: safeText(240).default(""),
    created_at: safeText(120).default(""),
    updated_at: safeText(120).default(""),
    last_seen_at: safeText(120).default(""),
    paired_at: safeText(120).default(""),
    metadata: z.record(z.string(), z.unknown()).default({}),
  })
  .passthrough();

export const channelUnknownSenderSchema = z
  .object({
    schema_version: z.literal("channel_gateway.v1").default("channel_gateway.v1"),
    identity_id: safeIdentifier(120),
    agent_id: safeIdentifier(120),
    channel_type: safeIdentifier(80),
    channel_id: safeText(240),
    user_id: safeText(240),
    display_name: safeText(240),
    is_group: z.boolean().default(false),
    message_id: safeText(240).default(""),
    message_preview: safeContent(500).default(""),
    status: z.literal("pending").default("pending"),
    first_seen_at: safeText(120).default(""),
    last_seen_at: safeText(120).default(""),
  })
  .passthrough();

export const channelPairingCodeSchema = z
  .object({
    schema_version: z.literal("channel_gateway.v1").default("channel_gateway.v1"),
    pairing_code_id: safeIdentifier(160),
    agent_id: safeIdentifier(120),
    channel_type: safeIdentifier(80),
    code: safeIdentifier(40),
    status: safeText(80).default("active"),
    created_by: safeText(240).default(""),
    created_at: safeText(120).default(""),
    expires_at: safeText(120).default(""),
    used_at: safeText(120).default(""),
  })
  .passthrough();

export const channelGatewaySummarySchema = z
  .object({
    allowed: z.number().int().nonnegative().default(0),
    blocked: z.number().int().nonnegative().default(0),
    pending: z.number().int().nonnegative().default(0),
    active_pairing_codes: z.number().int().nonnegative().default(0),
  })
  .passthrough();

export const channelGatewayStateSchema = z
  .object({
    schema_version: z.literal("channel_gateway.v1").default("channel_gateway.v1"),
    agent_id: safeIdentifier(120),
    pilot_channel: safeIdentifier(80).default("telegram"),
    status: z.enum(["ready", "pairing_required", "degraded"]).default("pairing_required"),
    legacy_allowed_user_ids: z.array(safeText(80)).max(500).default([]),
    identities: z.array(channelGatewayIdentitySchema).max(500).default([]),
    unknown_senders: z.array(channelUnknownSenderSchema).max(500).default([]),
    pairing_codes: z.array(channelPairingCodeSchema).max(50).default([]),
    summary: channelGatewaySummarySchema.default({
      allowed: 0,
      blocked: 0,
      pending: 0,
      active_pairing_codes: 0,
    }),
    error: operationalErrorEnvelopeSchema.nullable().optional(),
  })
  .passthrough();

export const createPairingCodeBodySchema = z
  .object({
    channel_type: safeIdentifier(80).default("telegram"),
    ttl_seconds: z.number().int().min(60).max(3600).default(900),
  })
  .partial();

export const channelGatewayDecisionBodySchema = z
  .object({
    rationale: safeContent(1000).optional(),
  })
  .partial();

export type ChannelGatewayState = z.infer<typeof channelGatewayStateSchema>;
export type ChannelGatewayIdentity = z.infer<typeof channelGatewayIdentitySchema>;
export type ChannelUnknownSender = z.infer<typeof channelUnknownSenderSchema>;
export type ChannelPairingCode = z.infer<typeof channelPairingCodeSchema>;

export function parseChannelGatewayState(raw: unknown): ChannelGatewayState {
  return channelGatewayStateSchema.parse(raw);
}

registerBodySchema({
  method: "POST",
  match: (segments) =>
    segments.length === 5 &&
    segments[0] === "agents" &&
    segments[2] === "channels" &&
    segments[3] === "gateway" &&
    segments[4] === "pairing-codes",
  schema: createPairingCodeBodySchema,
});

for (const action of ["approve", "block"] as const) {
  registerBodySchema({
    method: "POST",
    match: (segments) =>
      segments.length === 7 &&
      segments[0] === "agents" &&
      segments[2] === "channels" &&
      segments[3] === "gateway" &&
      segments[4] === "identities" &&
      segments[6] === action,
    schema: channelGatewayDecisionBodySchema,
  });
}
