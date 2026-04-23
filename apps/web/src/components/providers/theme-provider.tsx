"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  readDocumentCookie,
  safeLocalStorageGet,
  safeLocalStorageSetValue,
} from "@/lib/browser-storage";
import { themePreferenceStorageCodec } from "@/lib/storage-codecs";
import {
  applyThemeToDocumentRoot,
  DEFAULT_THEME_PREFERENCE,
  normalizeThemePreference,
  resolveThemePreference,
  type Theme,
  type ThemePreference,
} from "@/components/providers/theme";

export type ThemeContextValue = {
  themePreference: ThemePreference;
  theme: Theme;
  systemTheme: Theme;
  setThemePreference: (nextPreference: ThemePreference) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

const useIsomorphicLayoutEffect = typeof window !== "undefined" ? useLayoutEffect : useEffect;

function getSystemTheme(): Theme {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return "light";
  }

  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function readStoredThemePreference(fallback: ThemePreference): ThemePreference {
  if (typeof window === "undefined") {
    return fallback;
  }

  const rawPreference = safeLocalStorageGet(themePreferenceStorageCodec.key);

  if (rawPreference != null) {
    try {
      const parsedPreference = JSON.parse(rawPreference);

      if (typeof parsedPreference === "string") {
        return normalizeThemePreference(parsedPreference);
      }
    } catch {
      // Best effort; fall through to cookie/default fallback.
    }
  }

  const cookiePreference = readDocumentCookie(themePreferenceStorageCodec.key);
  if (cookiePreference != null) {
    return normalizeThemePreference(cookiePreference);
  }

  return fallback;
}

function persistThemePreference(preference: ThemePreference) {
  safeLocalStorageSetValue(themePreferenceStorageCodec, preference);
  document.cookie = `${themePreferenceStorageCodec.key}=${encodeURIComponent(preference)}; path=/; max-age=31536000; samesite=lax`;
}

function getFallbackThemeContextValue(): ThemeContextValue {
  const systemTheme = getSystemTheme();
  const documentTheme =
    typeof document !== "undefined"
      ? normalizeDocumentTheme(document.documentElement.dataset.theme)
      : null;
  const theme = documentTheme ?? systemTheme;

  return {
    themePreference: DEFAULT_THEME_PREFERENCE,
    theme,
    systemTheme,
    setThemePreference: () => {},
  };
}

function normalizeDocumentTheme(value?: string | null): Theme | null {
  if (value === "light" || value === "dark") {
    return value;
  }

  return null;
}

export function ThemeProvider({
  children,
  initialThemePreference = DEFAULT_THEME_PREFERENCE,
}: {
  children: ReactNode;
  initialThemePreference?: ThemePreference;
}) {
  // Use server-provided initial values to prevent hydration mismatch.
  // Client-side preferences are applied in useEffect below.
  const [themePreference, setThemePreferenceState] = useState<ThemePreference>(initialThemePreference);
  const [systemTheme, setSystemTheme] = useState<Theme>("dark");

  // Apply stored preference on client mount (after hydration)
  useEffect(() => {
    const stored = readStoredThemePreference(initialThemePreference);
    if (stored !== initialThemePreference) {
      setThemePreferenceState(stored);
    }
    setSystemTheme(getSystemTheme());
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (
      themePreference !== "system" ||
      typeof window === "undefined" ||
      typeof window.matchMedia !== "function"
    ) {
      return undefined;
    }

    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const updateSystemTheme = () => {
      setSystemTheme(mediaQuery.matches ? "dark" : "light");
    };

    updateSystemTheme();
    mediaQuery.addEventListener("change", updateSystemTheme);

    return () => {
      mediaQuery.removeEventListener("change", updateSystemTheme);
    };
  }, [themePreference]);

  const theme = resolveThemePreference(themePreference, systemTheme);

  useIsomorphicLayoutEffect(() => {
    if (typeof document === "undefined") {
      return;
    }

    applyThemeToDocumentRoot(document.documentElement, themePreference, theme);
    persistThemePreference(themePreference);
  }, [theme, themePreference]);

  const setThemePreference = useCallback((nextPreference: ThemePreference) => {
    setThemePreferenceState(nextPreference);
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({
      themePreference,
      theme,
      systemTheme,
      setThemePreference,
    }),
    [setThemePreference, systemTheme, theme, themePreference],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);

  return context ?? getFallbackThemeContextValue();
}
