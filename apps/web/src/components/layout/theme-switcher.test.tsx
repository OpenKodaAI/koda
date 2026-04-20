import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeSwitcher } from "@/components/layout/theme-switcher";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ThemeProvider } from "@/components/providers/theme-provider";
import { THEME_PREFERENCE_STORAGE_KEY } from "@/lib/storage-codecs";

type MatchMediaController = {
  setMatches: (matches: boolean) => void;
};

function installLocalStorage() {
  const store = new Map<string, string>();

  Object.defineProperty(window, "localStorage", {
    configurable: true,
    writable: true,
    value: {
      getItem: vi.fn((key: string) => store.get(key) ?? null),
      setItem: vi.fn((key: string, value: string) => {
        store.set(key, String(value));
      }),
      removeItem: vi.fn((key: string) => {
        store.delete(key);
      }),
      clear: vi.fn(() => {
        store.clear();
      }),
    },
  });
}

function mockMatchMedia(initialMatches: boolean): MatchMediaController {
  let matches = initialMatches;
  const listeners = new Set<(event: MediaQueryListEvent) => void>();

  const mediaQueryList = {
    media: "(prefers-color-scheme: dark)",
    get matches() {
      return matches;
    },
    onchange: null,
    addEventListener: vi.fn((event: string, listener: (event: MediaQueryListEvent) => void) => {
      if (event === "change") {
        listeners.add(listener);
      }
    }),
    removeEventListener: vi.fn((event: string, listener: (event: MediaQueryListEvent) => void) => {
      if (event === "change") {
        listeners.delete(listener);
      }
    }),
    addListener: vi.fn((listener: (event: MediaQueryListEvent) => void) => {
      listeners.add(listener);
    }),
    removeListener: vi.fn((listener: (event: MediaQueryListEvent) => void) => {
      listeners.delete(listener);
    }),
    dispatchEvent: vi.fn(),
  } as unknown as MediaQueryList;

  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: vi.fn(() => mediaQueryList),
  });

  return {
    setMatches(nextMatches: boolean) {
      matches = nextMatches;
      const event = { matches, media: mediaQueryList.media } as MediaQueryListEvent;
      listeners.forEach((listener) => listener(event));
    },
  };
}

function renderThemeSwitcher(initialPreference: "system" | "light" | "dark" = "system") {
  return render(
    <ThemeProvider initialThemePreference={initialPreference}>
      <I18nProvider initialLanguage="en-US">
        <ThemeSwitcher />
      </I18nProvider>
    </ThemeProvider>,
  );
}

describe("ThemeSwitcher", () => {
  beforeEach(() => {
    installLocalStorage();
    document.documentElement.dataset.theme = "";
    document.documentElement.classList.remove("dark");
    document.documentElement.style.colorScheme = "";
  });

  it("derives the initial document theme from the system preference", async () => {
    const media = mockMatchMedia(false);

    renderThemeSwitcher();

    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe("light");
    });

    act(() => {
      media.setMatches(true);
    });

    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe("dark");
      expect(document.documentElement.classList.contains("dark")).toBe(true);
    });
  });

  it("toggles between light and dark on click and persists the choice", async () => {
    mockMatchMedia(true);
    renderThemeSwitcher();

    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe("dark");
    });

    const button = screen.getByRole("button", { name: /Theme/i });
    fireEvent.click(button);

    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe("light");
      expect(window.localStorage.getItem(THEME_PREFERENCE_STORAGE_KEY)).toBe(JSON.stringify("light"));
    });

    fireEvent.click(screen.getByRole("button", { name: /Theme/i }));

    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe("dark");
      expect(window.localStorage.getItem(THEME_PREFERENCE_STORAGE_KEY)).toBe(JSON.stringify("dark"));
    });
  });

  it("reflects the active state through aria-pressed", async () => {
    mockMatchMedia(false);
    renderThemeSwitcher("light");

    const button = await screen.findByRole("button", { name: /Theme/i });
    expect(button).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(button);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Theme/i })).toHaveAttribute("aria-pressed", "true");
    });
  });
});
