import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AgentCatalogProvider } from "@/components/providers/agent-catalog-provider";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ComposerToolbar } from "@/components/sessions/chat/composer/composer-toolbar";

// D-332: the agent picker's options sat in li elements inside a ul with
// role=listbox, so the listitem role broke the listbox > option chain (axe
// aria-required-parent and aria-required-children).
const agents = ["ATLAS", "NOVA"].map((id) => ({
  id,
  label: id,
  color: "#22C7D8",
  colorRgb: "34, 199, 216",
  initials: id.slice(0, 2),
  status: "active" as const,
  model: "Claude Sonnet 4.6",
}));

describe("ComposerToolbar agent picker (D-332)", () => {
  it("puts every option directly in a named listbox", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider initialLanguage="en-US">
        <AgentCatalogProvider initialAgents={agents}>
          <ComposerToolbar agentId="ATLAS" onAgentChange={vi.fn()} lockedAgent={false} />
        </AgentCatalogProvider>
      </I18nProvider>,
    );
    await user.click(screen.getByRole("button", { name: /ATLAS/ }));
    const listbox = await screen.findByRole("listbox", { name: "Agents" });
    const options = within(listbox).getAllByRole("option");
    expect(options).toHaveLength(2);
    for (const option of options) expect(option.parentElement).toBe(listbox);
    expect(listbox.querySelector("ul, ol, li")).toBeNull();
    expect(within(listbox).getByRole("option", { name: "ATLAS" })).toHaveAttribute("aria-selected", "true");
    // The popover is a Radix dialog: it needs a name too (axe aria-dialog-name).
    expect(screen.getByRole("dialog", { name: "Agents" })).toContainElement(listbox);
  });
});
