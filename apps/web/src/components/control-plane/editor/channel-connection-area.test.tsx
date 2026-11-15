import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChannelConnectionArea } from "@/components/control-plane/editor/channel-connection-area";
import { CHANNEL_CATALOG } from "@/components/control-plane/editor/channel-catalog-data";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { translateForLanguage } from "@/lib/i18n";

// D-017 / F-CHN-06 (M6-E1-T2): no runtime code starts the eight non-Telegram
// adapters, so their cards read "Not available" and their credential forms are
// disabled, whatever secrets the agent already stores.

const editorState = vi.hoisted(() => ({
  secrets: [] as Array<{ secret_key: string }>,
}));

vi.mock("@/hooks/use-agent-editor", () => ({
  useAgentEditor: () => ({
    state: { agent: { id: "ATLAS", secrets: editorState.secrets } },
  }),
}));

vi.mock("@/lib/http-client", () => ({
  requestJson: vi.fn(async () => undefined),
  requestJsonAllowError: vi.fn(async () => ({ ok: true, data: { ok: true } })),
}));

const UNAVAILABLE_KEYS = [
  "whatsapp",
  "discord",
  "slack",
  "teams",
  "line",
  "messenger",
  "signal",
  "instagram",
];

function storeEveryRequiredSecret() {
  editorState.secrets = CHANNEL_CATALOG.flatMap((channel) =>
    channel.fields.filter((field) => field.required).map((field) => ({ secret_key: field.key })),
  );
}

function renderArea(language: "en-US" | "pt-BR") {
  return render(
    <I18nProvider initialLanguage={language}>
      <ChannelConnectionArea />
    </I18nProvider>,
  );
}

function tr(language: string, key: string) {
  return translateForLanguage(language, key);
}

describe("ChannelConnectionArea (M6-E1-T2)", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    // The provider prefers a persisted locale over `initialLanguage`.
    window.localStorage.clear();
    document.cookie = "atlas.locale=; max-age=0; path=/";
    storeEveryRequiredSecret();
    fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ display_id: "atlas_bot", display_name: "Atlas", allowed_users: [] }),
    }));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    editorState.secrets = [];
  });

  it("lists Telegram as the only available channel in the catalog", () => {
    expect(CHANNEL_CATALOG.filter((channel) => channel.available).map((channel) => channel.key)).toEqual([
      "telegram",
    ]);
    expect(
      CHANNEL_CATALOG.filter((channel) => !channel.available).map((channel) => channel.key),
    ).toEqual(UNAVAILABLE_KEYS);
  });

  for (const language of ["en-US", "pt-BR"] as const) {
    describe(language, () => {
      it("shows the eight adapters as not available, never connected, even with stored credentials", async () => {
        renderArea(language);
        const notAvailable = tr(language, "controlPlane.channelCatalog.unavailable.badge");
        const connected = tr(language, "generated.controlPlane.conectado_e04915ac");
        expect(notAvailable).not.toBe("controlPlane.channelCatalog.unavailable.badge");
        if (language === "en-US") expect(notAvailable).toBe("Not available");

        for (const key of UNAVAILABLE_KEYS) {
          const channel = CHANNEL_CATALOG.find((entry) => entry.key === key)!;
          const label = tr(language, channel.labelKey);
          const card = screen.getByRole("button", { name: `${label} — ${notAvailable}` });
          expect(card).toHaveAccessibleName(expect.not.stringContaining(connected));
          expect(within(card).getByText(notAvailable)).toBeInTheDocument();
        }

        // Telegram keeps its real status.
        const telegram = await screen.findByRole("button", { name: `Telegram — ${connected}` });
        expect(telegram).toBeInTheDocument();
        expect(screen.getAllByRole("button", { name: new RegExp(`— ${connected}$`) })).toHaveLength(1);

        // No status probe runs for a channel Koda never starts.
        const probed = fetchMock.mock.calls.map(([url]) => String(url));
        for (const key of UNAVAILABLE_KEYS) {
          expect(probed.some((url) => url.includes(`/${key}/`))).toBe(false);
        }
      });

      it("opens a disabled credential form that explains the channel does not run", async () => {
        const user = userEvent.setup();
        renderArea(language);
        const notAvailable = tr(language, "controlPlane.channelCatalog.unavailable.badge");
        const label = tr(language, "controlPlane.channelCatalog.entries.whatsapp.label");

        await user.click(screen.getByRole("button", { name: `${label} — ${notAvailable}` }));

        const dialog = await screen.findByRole("dialog");
        expect(
          within(dialog).getByText(tr(language, "controlPlane.channelCatalog.unavailable.title")),
        ).toBeInTheDocument();
        expect(
          within(dialog).getByText(tr(language, "controlPlane.channelCatalog.unavailable.description")),
        ).toBeInTheDocument();

        // Stored credentials never turn into a "connected" view.
        expect(within(dialog).queryByText("@atlas_bot")).not.toBeInTheDocument();
        expect(
          within(dialog).queryByRole("button", { name: tr(language, "generated.controlPlane.desconectar_d1a164af") }),
        ).not.toBeInTheDocument();

        const inputs = dialog.querySelectorAll("input");
        expect(inputs.length).toBe(4);
        for (const input of Array.from(inputs)) {
          expect(input).toBeDisabled();
          expect(input.className).toContain("disabled:opacity-60");
        }
        const revealButtons = within(dialog).getAllByRole("button", {
          name: tr(language, "generated.ui.visualizar_valor_1d66e788"),
        });
        expect(revealButtons.length).toBe(3);
        for (const button of revealButtons) {
          expect(button).toBeDisabled();
        }
        expect(
          within(dialog).getByRole("button", { name: tr(language, "generated.controlPlane.validar_e_conectar_16aa616f") }),
        ).toBeDisabled();
      });
    });
  }

  it("keeps the Telegram credential form enabled", async () => {
    editorState.secrets = [];
    const user = userEvent.setup();
    renderArea("en-US");

    await user.click(screen.getByRole("button", { name: "Telegram — Disconnected" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByText("Not available")).not.toBeInTheDocument();
    const token = dialog.querySelector('input[type="password"]');
    expect(token).not.toBeNull();
    expect(token).toBeEnabled();
    expect(within(dialog).getByRole("button", { name: "Validate and connect" })).toBeEnabled();
  });
});
