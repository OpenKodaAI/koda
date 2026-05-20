import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChannelGatewayMiniPanel } from "@/components/control-plane/editor/channel-connection-modal";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { requestJson } from "@/lib/http-client";

vi.mock("@/lib/http-client", () => ({
  requestJson: vi.fn(),
  requestJsonAllowError: vi.fn(),
}));

const requestJsonMock = vi.mocked(requestJson);

const gatewayState = {
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
      display_name: "Allowed User",
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
      display_name: "Pending User",
      message_preview: "hello",
    },
  ],
  pairing_codes: [
    {
      schema_version: "channel_gateway.v1",
      pairing_code_id: "chgpair_1",
      agent_id: "ATLAS",
      channel_type: "telegram",
      code: "PAIR123",
    },
  ],
  summary: {
    allowed: 1,
    blocked: 0,
    pending: 1,
    active_pairing_codes: 1,
  },
};

function renderPanel() {
  return render(
    <I18nProvider initialLanguage="pt-BR">
      <ChannelGatewayMiniPanel agentId="ATLAS" />
    </I18nProvider>,
  );
}

describe("ChannelGatewayMiniPanel", () => {
  beforeEach(() => {
    requestJsonMock.mockReset();
    requestJsonMock.mockImplementation(async () => gatewayState);
  });

  it("renders backend gateway state and sends approve/revoke actions through canonical APIs", async () => {
    const user = userEvent.setup();
    renderPanel();

    expect(await screen.findByText("Pending User")).toBeInTheDocument();
    expect(screen.getByText("PAIR123")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Aprovar" }));
    await waitFor(() =>
      expect(requestJsonMock).toHaveBeenCalledWith(
        "/api/control-plane/agents/ATLAS/channels/gateway/identities/chgid_pending/approve",
        { method: "POST", body: JSON.stringify({}) },
      ),
    );

    await user.click(screen.getByRole("button", { name: "Revogar" }));
    await waitFor(() =>
      expect(requestJsonMock).toHaveBeenCalledWith(
        "/api/control-plane/agents/ATLAS/channels/gateway/identities/chgid_allowed",
        { method: "DELETE" },
      ),
    );
  });
});
