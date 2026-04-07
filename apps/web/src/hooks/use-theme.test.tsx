import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@/components/providers/theme-provider";
import type { ThemePreference } from "@/components/providers/theme";
import { THEME_PREFERENCE_STORAGE_KEY } from "@/lib/storage-codecs";
import { useTheme } from "@/hooks/use-theme";

type MatchMediaMock = MediaQueryList & {
  dispatch: (matches: boolean) => void;
};

function createMatchMediaMock(initialMatches: boolean) {
  const listeners = new Set<(event: MediaQueryListEvent) => void>();
  let matches = initialMatches;

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
    dispatchEvent: vi.fn(() => true),
    dispatch(nextMatches: boolean) {
      matches = nextMatches;
      listeners.forEach((listener) => {
        listener({ matches: nextMatches } as MediaQueryListEvent);
      });
    },
  } as MatchMediaMock;

  return mediaQueryList;
}

function renderThemeHook(initialThemePreference: ThemePreference = "system") {
  return renderHook(() => useTheme(), {
    wrapper: ({ children }) => (
      <ThemeProvider initialThemePreference={initialThemePreference}>
        {children}
      </ThemeProvider>
    ),
  });
}

describe("useTheme", () => {
  beforeEach(() => {
    const storageState = new Map<string, string>();
    const localStorageMock = {
      getItem: vi.fn((key: string) => storageState.get(key) ?? null),
      setItem: vi.fn((key: string, value: string) => {
        storageState.set(key, String(value));
      }),
      removeItem: vi.fn((key: string) => {
        storageState.delete(key);
      }),
      clear: vi.fn(() => {
        storageState.clear();
      }),
    };

    Object.defineProperty(window, "localStorage", {
      value: localStorageMock,
      writable: true,
      configurable: true,
    });
    document.documentElement.className = "";
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.removeAttribute("data-theme-preference");
    document.documentElement.style.colorScheme = "";
    window.localStorage.clear();
    document.cookie = `${THEME_PREFERENCE_STORAGE_KEY}=; path=/; max-age=0`;
  });

  it("tracks the operating system theme when preference is system", async () => {
    const matchMedia = createMatchMediaMock(true);
    Object.defineProperty(window, "matchMedia", {
      value: vi.fn(() => matchMedia),
      configurable: true,
      writable: true,
    });

    const { result } = renderThemeHook("system");

    await waitFor(() => {
      expect(result.current.themePreference).toBe("system");
      expect(result.current.theme).toBe("dark");
      expect(document.documentElement.dataset.theme).toBe("dark");
    });

    act(() => {
      matchMedia.dispatch(false);
    });

    await waitFor(() => {
      expect(result.current.theme).toBe("light");
      expect(document.documentElement.dataset.theme).toBe("light");
      expect(document.documentElement.classList.contains("dark")).toBe(false);
    });
  });

  it("persists explicit light and dark preferences", async () => {
    const matchMedia = createMatchMediaMock(false);
    Object.defineProperty(window, "matchMedia", {
      value: vi.fn(() => matchMedia),
      configurable: true,
      writable: true,
    });

    const { result } = renderThemeHook("system");

    await waitFor(() => {
      expect(result.current.theme).toBe("light");
    });

    act(() => {
      result.current.setThemePreference("dark");
    });

    await waitFor(() => {
      expect(result.current.themePreference).toBe("dark");
      expect(result.current.theme).toBe("dark");
      expect(document.documentElement.dataset.theme).toBe("dark");
      expect(document.documentElement.classList.contains("dark")).toBe(true);
    });

    expect(window.localStorage.getItem(THEME_PREFERENCE_STORAGE_KEY)).toBe(JSON.stringify("dark"));
    expect(document.cookie).toContain(`${THEME_PREFERENCE_STORAGE_KEY}=dark`);

    act(() => {
      matchMedia.dispatch(true);
    });

    await waitFor(() => {
      expect(result.current.theme).toBe("dark");
      expect(document.documentElement.dataset.theme).toBe("dark");
    });
  });

  it("only subscribes to system changes while preference is system", async () => {
    const matchMedia = createMatchMediaMock(false);
    const matchMediaSpy = vi.fn(() => matchMedia);
    Object.defineProperty(window, "matchMedia", {
      value: matchMediaSpy,
      configurable: true,
      writable: true,
    });

    const { result } = renderThemeHook("dark");

    await waitFor(() => {
      expect(result.current.themePreference).toBe("dark");
      expect(result.current.theme).toBe("dark");
    });

    expect(matchMedia.addEventListener).not.toHaveBeenCalled();

    act(() => {
      result.current.setThemePreference("system");
    });

    await waitFor(() => {
      expect(result.current.themePreference).toBe("system");
    });

    expect(matchMedia.addEventListener).toHaveBeenCalledWith("change", expect.any(Function));
  });
});
