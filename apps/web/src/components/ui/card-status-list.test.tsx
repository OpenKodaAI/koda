import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AnimatedCardStatusList, type Card } from "@/components/ui/card-status-list";

const cards: Card[] = [
  { id: "healthy", title: "Runtime layers healthy", status: "completed" },
  { id: "backlog", title: "Recovery backlog", status: "updates-found" },
  { id: "active", title: "Active execution rooms", status: "syncing" },
];

describe("AnimatedCardStatusList", () => {
  it("renders a Koda status card without optional header actions", () => {
    render(<AnimatedCardStatusList title="Runtime status" cards={cards} sort="attention-first" />);

    const panel = screen.getByTestId("animated-card-status-list");
    expect(within(panel).getByText("Runtime status")).toBeInTheDocument();
    expect(within(panel).getByText("Recovery backlog")).toBeInTheDocument();
    expect(within(panel).getByText("Active execution rooms")).toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "Back" })).not.toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "Add card" })).not.toBeInTheDocument();
    expect(panel.querySelector('[data-card-status="updates-found"]')).toBeInTheDocument();
    expect(panel.querySelector('[data-card-status="syncing"]')).toBeInTheDocument();
  });

  it("shows synchronize action for update cards and calls the handler", async () => {
    const onSynchronize = vi.fn();
    const user = userEvent.setup();
    render(
      <AnimatedCardStatusList
        title="Eval readiness"
        cards={cards}
        onSynchronize={onSynchronize}
        synchronizeLabel="Sync"
      />,
    );

    const updateCard = screen.getByText("Recovery backlog").closest("[data-card-status]");
    expect(updateCard).not.toBeNull();
    await user.hover(updateCard as HTMLElement);
    await user.click(await screen.findByRole("button", { name: "Sync" }));

    expect(onSynchronize).toHaveBeenCalledWith("backlog");
  });
});
