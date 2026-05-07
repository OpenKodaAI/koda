import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  applyThemeToDocumentRoot,
  buildThemeBootstrapScript,
  normalizeThemePreference,
  resolveThemePreference,
} from "@/components/providers/theme";
import { THEME_PREFERENCE_STORAGE_KEY } from "@/lib/storage-codecs";

describe("theme helpers", () => {
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

  it("normalizes preference values and resolves the effective theme", () => {
    expect(normalizeThemePreference(" dark ")).toBe("dark");
    expect(normalizeThemePreference("LIGHT")).toBe("light");
    expect(normalizeThemePreference("anything-else")).toBe("system");
    expect(resolveThemePreference("system", "dark")).toBe("dark");
    expect(resolveThemePreference("light", "dark")).toBe("light");
  });

  it("applies the effective theme to the document root", () => {
    applyThemeToDocumentRoot(document.documentElement, "system", "light");

    expect(document.documentElement.dataset.themePreference).toBe("system");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(document.documentElement.style.colorScheme).toBe("light");
  });

  it("bootstraps the stored preference before hydration", () => {
    window.localStorage.setItem(
      THEME_PREFERENCE_STORAGE_KEY,
      JSON.stringify("dark"),
    );
    Object.defineProperty(window, "matchMedia", {
      value: vi.fn().mockReturnValue({
        matches: false,
        media: "(prefers-color-scheme: dark)",
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      } as MediaQueryList),
      configurable: true,
      writable: true,
    });

    new Function(
      buildThemeBootstrapScript({
        storageKey: THEME_PREFERENCE_STORAGE_KEY,
        cookieKey: THEME_PREFERENCE_STORAGE_KEY,
      }),
    )();

    expect(document.documentElement.dataset.themePreference).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });
});
