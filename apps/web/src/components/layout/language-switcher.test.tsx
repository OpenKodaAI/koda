import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

  it("fades a copy of the menu out after Radix has closed it", async () => {
    const trigger = renderSwitcher();
    const listbox = await openWithKeyboard(trigger, "ArrowDown");
    expect(listbox.className).toContain("animate-in");
    const english = screen.getByRole("option", { name: /English/ });
    await waitFor(() => expect(document.activeElement).toBe(english));

    fireEvent.keyDown(english, { key: "Escape" });

    // The live list is gone at once; what stays on screen is an inert copy.
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    const ghost = document.querySelector<HTMLElement>(".language-switcher__menu");
    expect(ghost).not.toBeNull();
    expect(ghost).not.toBe(listbox);
    expect(ghost?.className).toContain("animate-out");
    const frame = ghost?.parentElement;
    expect(frame).toHaveAttribute("aria-hidden", "true");
    expect(frame).toHaveAttribute("inert");
    expect(frame?.style.pointerEvents).toBe("none");
    // Radix sets pointer-events: auto inline on the list; the copy drops it.
    expect(ghost?.style.pointerEvents).toBe("none");
    await waitFor(() =>
      expect(document.querySelector(".language-switcher__menu")).not.toBeInTheDocument(),
    );
  });

  it("does not pick the highlighted language when Enter follows Escape during the fade", async () => {
    const trigger = renderSwitcher();
    await openWithKeyboard(trigger, "ArrowDown");
    const english = screen.getByRole("option", { name: /English/ });
    await waitFor(() => expect(document.activeElement).toBe(english));
    fireEvent.keyDown(english, { key: "ArrowDown" });
    const portuguese = screen.getByRole("option", { name: /Português/ });
    await waitFor(() => expect(document.activeElement).toBe(portuguese));

    fireEvent.keyDown(portuguese, { key: "Escape" });
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Enter" });

    expect(trigger).toHaveTextContent("EN");
    expect(trigger).not.toHaveTextContent("PT-BR");
  });

  it("hands focus and the page back at once, so Tab moves on during the fade", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider initialLanguage="en-US">
        <LanguageSwitcher />
        <button type="button">Theme</button>
      </I18nProvider>,
    );
    const trigger = screen.getByRole("combobox", { name: "Language" });
    await openWithKeyboard(trigger, "ArrowDown");
    const english = screen.getByRole("option", { name: /English/ });
    await waitFor(() => expect(document.activeElement).toBe(english));

    fireEvent.keyDown(english, { key: "Escape" });
    // Radix returns focus on its next tick; the fade lasts 160ms.
    await act(() => new Promise((resolve) => window.setTimeout(resolve, 20)));

    expect(document.activeElement).toBe(trigger);
    expect(document.body.style.pointerEvents).not.toBe("none");
    await user.tab();
    expect(screen.getByRole("button", { name: "Theme" })).toHaveFocus();
  });

  it("ignores clicks on the fading copy of the menu", async () => {
    const trigger = renderSwitcher();
    await openWithKeyboard(trigger, "ArrowDown");
    const english = screen.getByRole("option", { name: /English/ });
    await waitFor(() => expect(document.activeElement).toBe(english));

    fireEvent.keyDown(english, { key: "Escape" });
    const fading = document.querySelector<HTMLElement>(".language-switcher__menu");
    const deutsch = [...(fading?.querySelectorAll<HTMLElement>("[data-radix-collection-item]") ?? [])].find(
      (option) => option.textContent?.includes("Deutsch"),
    );
    expect(deutsch, "the fading copy shows the options").toBeDefined();
    fireEvent.pointerDown(deutsch as HTMLElement, { pointerType: "mouse" });
    fireEvent.pointerUp(deutsch as HTMLElement, { pointerType: "mouse" });
    fireEvent.click(deutsch as HTMLElement);

    expect(trigger).toHaveTextContent("EN");
    await waitFor(() =>
      expect(document.querySelector(".language-switcher__menu")).not.toBeInTheDocument(),
    );
    expect(trigger).toHaveTextContent("EN");
  });
});
