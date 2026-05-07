import { useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { AgentCatalogProvider } from "@/components/providers/agent-catalog-provider";
import { ChatComposer } from "@/components/sessions/chat/chat-composer";
import type { ChatCommand } from "@/lib/contracts/chat-commands";

const agentCatalog = [
  {
    id: "ATLAS",
    label: "ATLAS",
    color: "#ff5a5a",
    colorRgb: "255, 90, 90",
    initials: "MA",
    status: "active" as const,
    model: "Claude Opus 4.6",
  },
];

function ComposerHarness(props: {
  onSubmit?: () => void;
  onCommandExecute?: (command: ChatCommand) => void;
}) {
  const [value, setValue] = useState("");
  return (
    <ChatComposer
      value={value}
      onChange={setValue}
      onSubmit={props.onSubmit ?? (() => {})}
      agentId="ATLAS"
      onCommandExecute={props.onCommandExecute}
    />
  );
}

function renderHarness(props: Partial<React.ComponentProps<typeof ComposerHarness>> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider initialLanguage="en-US">
        <AgentCatalogProvider initialAgents={agentCatalog}>
          <ComposerHarness {...props} />
        </AgentCatalogProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("ChatComposer slash menu", () => {
  beforeEach(() => {
    // Force fetch failures so the static fallback is used; gives deterministic
    // command set for assertions.
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));
  });

  it("opens with the static fallback commands when '/' is typed", async () => {
    const user = userEvent.setup();
    renderHarness();

    const textarea = screen.getByPlaceholderText(/Send a message/i);
    await user.click(textarea);
    await user.keyboard("/");

    const listbox = await screen.findByRole("listbox");
    expect(listbox).toBeInTheDocument();
    expect(await screen.findByRole("option", { name: /\/new-session/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /\/clear/i })).toBeInTheDocument();
  });

  it("filters commands as the user keeps typing", async () => {
    const user = userEvent.setup();
    renderHarness();

    const textarea = screen.getByPlaceholderText(/Send a message/i);
    await user.click(textarea);
    await user.keyboard("/sum");

    await waitFor(() => {
      expect(screen.getByRole("option", { name: /\/summarize/i })).toBeInTheDocument();
    });
    expect(screen.queryByRole("option", { name: /\/new-session/i })).toBeNull();
  });

  it("navigates with ArrowDown and selects with Enter (execute action)", async () => {
    const user = userEvent.setup();
    const onCommandExecute = vi.fn();
    renderHarness({ onCommandExecute });

    const textarea = screen.getByPlaceholderText(/Send a message/i) as HTMLTextAreaElement;
    await user.click(textarea);
    await user.keyboard("/");

    await screen.findByRole("listbox");
    // Press Enter — the first item (new-session) is selected by default.
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(onCommandExecute).toHaveBeenCalledTimes(1);
    });
    expect(onCommandExecute).toHaveBeenCalledWith(
      expect.objectContaining({ id: "new-session" }),
    );
    // The trigger token has been cleared from the textarea.
    expect(textarea.value).toBe("");
  });

  it("closes the menu on Escape and re-opens on next slash", async () => {
    const user = userEvent.setup();
    renderHarness();

    const textarea = screen.getByPlaceholderText(/Send a message/i) as HTMLTextAreaElement;
    await user.click(textarea);
    await user.keyboard("/");

    await screen.findByRole("listbox");
    await user.keyboard("{Escape}");

    await waitFor(() => {
      expect(screen.queryByRole("listbox")).toBeNull();
    });

    // After dismissing, type more — the menu stays closed for the same trigger.
    await user.keyboard("ne");
    await waitFor(() => {
      expect(screen.queryByRole("listbox")).toBeNull();
    });

    // Move past the trigger token (newline boundary) and re-trigger.
    await user.keyboard("{Enter}/");
    await screen.findByRole("listbox");
  });

  it("does not open on '/' inside a URL token", async () => {
    const user = userEvent.setup();
    renderHarness();

    const textarea = screen.getByPlaceholderText(/Send a message/i);
    await user.click(textarea);
    await user.keyboard("https://");

    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("listbox")).toBeNull();
  });
});
