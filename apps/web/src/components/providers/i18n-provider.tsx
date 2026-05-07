"use client";

import { I18nextProvider } from "react-i18next";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  DEFAULT_LANGUAGE,
  getI18nInstance,
  LANGUAGE_OPTIONS,
  LOCALE_COOKIE_KEY,
  normalizeLanguage,
  setCurrentLanguage,
  type AppLanguage,
} from "@/lib/i18n";
import {
  readDocumentCookie,
  safeLocalStorageGet,
  safeLocalStorageSetValue,
} from "@/lib/browser-storage";
import { localeStorageCodec } from "@/lib/storage-codecs";

type AppI18nContextValue = {
  language: AppLanguage;
  setLanguage: (language: AppLanguage) => void;
  options: typeof LANGUAGE_OPTIONS;
};

const AppI18nContext = createContext<AppI18nContextValue>({
  language: DEFAULT_LANGUAGE,
  setLanguage: () => undefined,
  options: LANGUAGE_OPTIONS,
});

export function I18nProvider({
  children,
  initialLanguage,
}: {
  children: ReactNode;
  initialLanguage?: string | null;
}) {
  const fallbackLanguage = normalizeLanguage(initialLanguage);
  setCurrentLanguage(fallbackLanguage);
  const i18n = getI18nInstance();
  // Use the server-provided language for initial render to avoid hydration mismatch.
  // localStorage/cookie preferences are applied in the useEffect below (client-only).
  const [language, setLanguageState] = useState<AppLanguage>(fallbackLanguage);

  // On mount (client-only), apply persisted language preference from storage
  useEffect(() => {
    const persisted = safeLocalStorageGet(localeStorageCodec.key);
    if (persisted) {
      const parsed = localeStorageCodec.parse(persisted);
      if (parsed !== fallbackLanguage) {
        setLanguageState(parsed);
        return; // The next effect will handle syncing
      }
    }
    const cookie = readDocumentCookie(LOCALE_COOKIE_KEY);
    if (cookie) {
      const normalized = normalizeLanguage(cookie);
      if (normalized !== fallbackLanguage) {
        setLanguageState(normalized);
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setCurrentLanguage(language);
    void i18n.changeLanguage(language);
    safeLocalStorageSetValue(localeStorageCodec, language);

    document.documentElement.lang = language;
    document.cookie = `${LOCALE_COOKIE_KEY}=${language}; path=/; max-age=31536000; samesite=lax`;
  }, [i18n, language]);

  const setLanguage = useCallback((nextLanguage: AppLanguage) => {
    setCurrentLanguage(nextLanguage);
    safeLocalStorageSetValue(localeStorageCodec, nextLanguage);

    document.documentElement.lang = nextLanguage;
    document.cookie = `${LOCALE_COOKIE_KEY}=${nextLanguage}; path=/; max-age=31536000; samesite=lax`;
    setLanguageState(nextLanguage);
  }, [setLanguageState]);

  const value = useMemo(
    () => ({
      language,
      setLanguage,
      options: LANGUAGE_OPTIONS,
    }),
    [language, setLanguage],
  );

  return (
    <AppI18nContext.Provider value={value}>
      <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
    </AppI18nContext.Provider>
  );
}

export function useI18nProvider() {
  return useContext(AppI18nContext);
}
