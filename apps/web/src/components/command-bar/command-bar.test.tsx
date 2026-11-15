import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CommandBar } from "@/components/command-bar/command-bar";
import type { CommandBarContext } from "@/components/command-bar/command-registry";

// M8-E1-T1 (D-114): on Home the inline dropdown is portaled over the page at
// z-index 90, so it must not stay open once focus leaves the input, or it
// hides the focused quick actions below it. The bar's own focus styling must
// follow real focus, not React state.

const ctx: CommandBarContext = {
  agents: [],
  stats: [],
  router: { push: vi.fn() },
  t: (key) => key,
  openAgentDetail: vi.fn(),
};

function renderBar() {
  render(
    <>
      <CommandBar
        ctx={ctx}
        mode="inline"
        placeholder="Search commands"
        emptyState="Nothing found"
        pillsSlot={<button type="button">Run task</button>}
      />
      <button type="button">After the bar</button>
    </>,
  );
  return screen.getByRole("combobox", { name: "Search commands" });
}

function barFrame(input: HTMLElement): HTMLElement {
  const frame = input.parentElement;
  if (!frame) throw new Error("command bar frame not rendered");
  return frame;
}

describe("CommandBar inline dropdown (M8-E1-T1)", () => {
  it("opens while the input has focus", async () => {
    const input = renderBar();
    await userEvent.setup().click(input);
    expect(await screen.findByRole("listbox")).toBeInTheDocument();
  });

  it("closes when Tab moves focus to a quick action inside the bar", async () => {
    const user = userEvent.setup();
    const input = renderBar();
    await user.click(input);
    await screen.findByRole("listbox");

    await user.tab();

    expect(screen.getByRole("button", { name: "Run task" })).toHaveFocus();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(input).toHaveAttribute("aria-expanded", "false");
  });

  it("closes when focus leaves with a query typed", async () => {
    const user = userEvent.setup();
    const input = renderBar();
    await user.click(input);
    await user.keyboard("home");
    await screen.findByRole("listbox");

    await user.tab();
    await user.tab();

    expect(screen.getByRole("button", { name: "After the bar" })).toHaveFocus();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("styles the bar with :focus-within, never from state", async () => {
    const user = userEvent.setup();
    const input = renderBar();
    const frame = barFrame(input);
    const classes = () => frame.className.split(/\s+/);

    for (const required of [
      "focus-within:border-[var(--focus-ring)]",
      "focus-within:outline",
      "focus-within:outline-[color:var(--focus-ring)]",
    ]) {
      expect(classes()).toContain(required);
    }

    await user.click(input);
    // No unconditional ring classes are added while the input has focus...
    expect(classes()).not.toContain("outline");
    expect(classes()).not.toContain("border-[var(--focus-ring)]");

    await user.tab();
    // ...so nothing can linger once focus has moved to a quick action.
    expect(classes()).not.toContain("outline");
    expect(classes()).not.toContain("border-[var(--focus-ring)]");
  });
});
