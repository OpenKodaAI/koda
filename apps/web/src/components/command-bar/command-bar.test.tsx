import { render, screen, within } from "@testing-library/react";
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

  it("points aria-activedescendant at a rendered option only while the list is open", async () => {
    // A closed combobox that names an option id the document does not hold
    // fails axe's aria-valid-attr-value (critical) on Home.
    const user = userEvent.setup();
    const input = renderBar();
    expect(input).not.toHaveAttribute("aria-activedescendant");

    await user.click(input);
    await screen.findByRole("listbox");
    const active = input.getAttribute("aria-activedescendant");
    expect(active).toBeTruthy();
    expect(document.getElementById(active ?? "")).toHaveAttribute("role", "option");

    await user.keyboard("zzzz-no-such-command");
    expect(screen.getByText("Nothing found")).toBeInTheDocument();
    expect(input).not.toHaveAttribute("aria-activedescendant");

    await user.clear(input);
    await user.keyboard("home");
    expect(input).toHaveAttribute("aria-activedescendant");

    // Leaving with a query typed keeps the query but closes the list.
    await user.tab();
    expect(input).toHaveValue("home");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(input).not.toHaveAttribute("aria-activedescendant");
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

// D-282: axe reported aria-required-parent (critical) on every option and
// aria-required-children on the listbox, because the options sat in plain
// ul/li elements, whose list and listitem roles broke the ownership chain.
const IMPLICIT_ROLES: Record<string, string> = { UL: "list", OL: "list", LI: "listitem" };

/** The roles between an option and the listbox, skipping generic and presentational elements. */
function rolesBetween(option: HTMLElement, listbox: HTMLElement): string[] {
  const roles: string[] = [];
  for (let node = option.parentElement; node && node !== listbox; node = node.parentElement) {
    const role = node.getAttribute("role") ?? IMPLICIT_ROLES[node.tagName] ?? null;
    if (role && role !== "presentation" && role !== "none") roles.push(role);
  }
  return roles;
}

describe("CommandBar listbox structure (D-282)", () => {
  it("owns every option directly or through one labelled group", async () => {
    const user = userEvent.setup();
    const input = renderBar();
    await user.click(input);
    const listbox = await screen.findByRole("listbox");
    const options = within(listbox).getAllByRole("option");
    expect(options.length).toBeGreaterThan(1);
    for (const option of options) {
      const roles = rolesBetween(option, listbox);
      expect(roles.every((role) => role === "group") && roles.length <= 1, `${option.id}: ${roles}`).toBe(true);
    }
    const groups = within(listbox).getAllByRole("group");
    expect(groups.length).toBeGreaterThan(0);
    for (const group of groups) {
      const heading = document.getElementById(group.getAttribute("aria-labelledby") ?? "");
      expect(heading?.textContent?.trim(), "each group is named by its heading").toBeTruthy();
      expect(within(group).getAllByRole("option").length).toBeGreaterThan(0);
    }
  });

  it("moves aria-activedescendant through the grouped options with the arrow keys", async () => {
    const user = userEvent.setup();
    const input = renderBar();
    await user.click(input);
    const listbox = await screen.findByRole("listbox");
    const options = within(listbox).getAllByRole("option");
    expect(input).toHaveAttribute("aria-activedescendant", options[0].id);
    expect(options[0]).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{ArrowDown}");
    expect(input).toHaveAttribute("aria-activedescendant", options[1].id);
    expect(options[1]).toHaveAttribute("aria-selected", "true");
    expect(options[0]).toHaveAttribute("aria-selected", "false");

    await user.keyboard("{ArrowUp}");
    expect(input).toHaveAttribute("aria-activedescendant", options[0].id);
  });
});


// M8-E5-T3: text in the palette stays on the type scale (12 / 13 / 14 …),
// through Tailwind's text-xs or a --font-size-* token, with no arbitrary px
// or rem size and nothing under the 12px floor. The global .eyebrow class
// sets 10.5px outside any layer, so it beats every size utility: it is off
// the scale too.
const OFF_SCALE = /^(?:text-\[(?:\d|\.)[\d.]*(?:px|rem)\]|eyebrow)$/;

describe("CommandBar type scale (M8-E5-T3)", () => {
  it("sets no arbitrary font size on the group headings, options or descriptions", async () => {
    render(
      <CommandBar
        ctx={{ ...ctx, agents: [{ id: "ATLAS", label: "Atlas", color: "#D97757", colorRgb: "217, 119, 87" }] }}
        mode="modal"
        placeholder="Search commands"
        emptyState="Nothing found"
      />,
    );
    const listbox = await screen.findByRole("listbox");
    const option = within(listbox).getByRole("option", { name: /Atlas/ });
    expect(option.textContent).toContain("commandBar.agent.description");
    const sized = [listbox, ...listbox.querySelectorAll<HTMLElement>("*")].flatMap((element) =>
      [...element.classList].filter((name) => OFF_SCALE.test(name)).map((name) => `${element.tagName.toLowerCase()} ${name}`),
    );
    expect(sized).toEqual([]);
  });
});
