import { describe, expect, it } from "vitest";
import "@/lib/contracts/channel-gateway";
import {
  channelGatewayDecisionBodySchema,
  createPairingCodeBodySchema,
  parseChannelGatewayState,
} from "@/lib/contracts/channel-gateway";
import { resolveBodySchema } from "@/lib/contracts/proxy-body-schemas";

describe("Phase 6 channel gateway contracts", () => {
  it("parses channel_gateway.v1 state without reclassifying backend decisions", () => {
    const state = parseChannelGatewayState({
      schema_version: "channel_gateway.v1",
      agent_id: "ATLAS",
      pilot_channel: "telegram",
      status: "pairing_required",
      legacy_allowed_user_ids: [],
      identities: [
        {
          schema_version: "channel_gateway.v1",
          identity_id: "chgid_allowed",
          agent_id: "ATLAS",
          channel_type: "telegram",
          channel_id: "-10042",
          user_id: "12345",
          display_name: "Operator",
          status: "allowed",
          source: "operator_approval",
        },
      ],
      unknown_senders: [
        {
          schema_version: "channel_gateway.v1",
          identity_id: "chgid_pending",
          agent_id: "ATLAS",
          channel_type: "telegram",
          channel_id: "-10099",
          user_id: "999",
          display_name: "Unknown",
          message_preview: "hello",
        },
      ],
      pairing_codes: [
        {
          schema_version: "channel_gateway.v1",
          pairing_code_id: "chgpair_1",
          agent_id: "ATLAS",
          channel_type: "telegram",
          code: "ABC123",
        },
      ],
      summary: {
        allowed: 1,
        blocked: 0,
        pending: 1,
        active_pairing_codes: 1,
      },
    });

    expect(state.identities[0]?.display_name).toBe("Operator");
    expect(state.unknown_senders[0]?.message_preview).toBe("hello");
    expect(state.summary.pending).toBe(1);
    expect(state.pairing_codes[0]?.code).toBe("ABC123");
  });

  it("registers gateway proxy body schemas for mutating routes", () => {
    const pairingSchema = resolveBodySchema("POST", [
      "agents",
      "ATLAS",
      "channels",
      "gateway",
      "pairing-codes",
    ]);
    const approveSchema = resolveBodySchema("POST", [
      "agents",
      "ATLAS",
      "channels",
      "gateway",
      "identities",
      "chgid_pending",
      "approve",
    ]);
    const blockSchema = resolveBodySchema("POST", [
      "agents",
      "ATLAS",
      "channels",
      "gateway",
      "identities",
      "chgid_pending",
      "block",
    ]);

    expect(pairingSchema).toBe(createPairingCodeBodySchema);
    expect(approveSchema).toBe(channelGatewayDecisionBodySchema);
    expect(blockSchema).toBe(channelGatewayDecisionBodySchema);
    expect(pairingSchema?.parse({ channel_type: "telegram", ttl_seconds: 900 })).toEqual({
      channel_type: "telegram",
      ttl_seconds: 900,
    });
  });
});
