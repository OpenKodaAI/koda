import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceTopbar } from "@/components/layout/workspace-topbar";
import { AppTourProvider } from "@/components/providers/app-tour-provider";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ThemeProvider } from "@/components/providers/theme-provider";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({
    push: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
    replace: vi.fn(),
  }),
}));

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

function installMatchMedia(matches = false) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: vi.fn(() => ({
      media: "(prefers-color-scheme: dark)",
      matches,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

describe("WorkspaceTopbar", () => {
  it("renders the theme switcher immediately before the language switcher", () => {
    installLocalStorage();
    installMatchMedia(false);

    render(
      <ThemeProvider initialThemePreference="system">
        <I18nProvider initialLanguage="en-US">
          <AppTourProvider
            pathname="/"
            mobileNavOpen={false}
            onMobileNavOpenChange={() => {}}
          >
            <WorkspaceTopbar />
          </AppTourProvider>
        </I18nProvider>
      </ThemeProvider>,
    );

    const themeButton = screen.getByRole("button", { name: /Theme/i });
    const languageButton = screen.getByRole("button", { name: /Language/i });

    expect(themeButton.compareDocumentPosition(languageButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
