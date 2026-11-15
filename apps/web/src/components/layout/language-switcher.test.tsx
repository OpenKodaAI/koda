import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { LanguageSwitcher } from "@/components/layout/language-switcher";
import { I18nProvider } from "@/components/providers/i18n-provider";

// M8-E1-T2 (D-115, F-WEB-09): the language switcher must work from the
// keyboard: arrow keys move between languages, Enter picks one, Escape
// closes, and focus moves into the list and back to the trigger.

beforeEach(() => {
  // The provider persists the chosen language; start every test in English.
  window.localStorage.clear();
  document.cookie.split(";").forEach((cookie) => {
    const name = cookie.split("=")[0]?.trim();
    if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
  });
});

function renderSwitcher() {
  render(
    <I18nProvider initialLanguage="en-US">
      <LanguageSwitcher />
    </I18nProvider>,
  );
  // Found by its tour anchor so the behaviour checks below do not depend on
  // the trigger's role; the first test pins the role separately.
  const trigger = document.querySelector<HTMLElement>(
    '[data-tour-anchor="shell.topbar.language-switcher.trigger"]',
  );
  if (!trigger) throw new Error("language switcher trigger not rendered");
  return trigger;
}

async function openWithKeyboard(trigger: HTMLElement, key: string) {
  act(() => trigger.focus());
  fireEvent.keyDown(trigger, { key });
  return screen.findByRole("listbox");
}

describe("LanguageSwitcher keyboard support (M8-E1-T2)", () => {
  it("opens from the keyboard and moves focus to the current language", async () => {
    const trigger = renderSwitcher();
    expect(screen.getByRole("combobox", { name: "Language" })).toBe(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    await openWithKeyboard(trigger, "ArrowDown");

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole("option", { name: /English/ })),
    );
    expect(screen.getByRole("option", { name: /English/ })).toHaveAttribute("aria-selected", "true");
  });

  it("moves with the arrow keys and picks a language with Enter", async () => {
    const trigger = renderSwitcher();
    await openWithKeyboard(trigger, "Enter");
    const english = screen.getByRole("option", { name: /English/ });
    await waitFor(() => expect(document.activeElement).toBe(english));

    fireEvent.keyDown(english, { key: "ArrowDown" });
    const portuguese = screen.getByRole("option", { name: /Português/ });
    await waitFor(() => expect(document.activeElement).toBe(portuguese));

    fireEvent.keyDown(portuguese, { key: "Enter" });

    await waitFor(() => expect(screen.queryByRole("listbox")).not.toBeInTheDocument());
    expect(trigger).toHaveTextContent("PT-BR");
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });

  it("closes with Escape, keeps the language and returns focus to the trigger", async () => {
    const trigger = renderSwitcher();
    await openWithKeyboard(trigger, "ArrowDown");
    const english = screen.getByRole("option", { name: /English/ });
    await waitFor(() => expect(document.activeElement).toBe(english));
    fireEvent.keyDown(english, { key: "ArrowDown" });

    fireEvent.keyDown(document.activeElement ?? english, { key: "Escape" });

    await waitFor(() => expect(screen.queryByRole("listbox")).not.toBeInTheDocument());
    expect(trigger).toHaveTextContent("EN");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });

  it("keeps the label styles on every option", async () => {
    const trigger = renderSwitcher();
    await openWithKeyboard(trigger, "ArrowDown");

    for (const [name, label] of [
      [/English/, "English (US)"],
      [/Português/, "Português (Brasil)"],
    ] as const) {
      const option = screen.getByRole("option", { name });
      const labelElement = option.querySelector(".language-switcher__option-label");
      expect(labelElement, `${label} option renders the label wrapper`).not.toBeNull();
      expect(within(labelElement as HTMLElement).getByText(label)).toBeInTheDocument();
    }
  });

  it("fades the menu out before it unmounts", async () => {
    const trigger = renderSwitcher();
    const listbox = await openWithKeyboard(trigger, "ArrowDown");
    expect(listbox.className).toContain("animate-in");
    const english = screen.getByRole("option", { name: /English/ });
    await waitFor(() => expect(document.activeElement).toBe(english));

    fireEvent.keyDown(english, { key: "Escape" });

    // Still mounted for the exit animation, and no longer clickable.
    expect(screen.getByRole("listbox")).toBe(listbox);
    expect(listbox.className).toContain("animate-out");
    expect(listbox.className).toContain("pointer-events-none");
    await waitFor(() => expect(screen.queryByRole("listbox")).not.toBeInTheDocument());
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });
});
