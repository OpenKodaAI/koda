"use client";

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useI18nProvider } from "@/components/providers/i18n-provider";
import { translateForLanguage, translateLiteralForLanguage } from "@/lib/i18n";

export function useAppI18n() {
  const { i18n } = useTranslation();
  const { language, setLanguage, options } = useI18nProvider();
  const translate = useMemo(
    () => (key: string, options?: Record<string, unknown>) =>
      translateForLanguage(language, key, options),
    [language],
  );
  const t = useMemo(
    () => (key: string, options?: Record<string, unknown>) => translate(key, options),
    [translate],
  );
  const tl = useMemo(
    () => (value: string, options?: Record<string, unknown>) =>
      translateLiteralForLanguage(language, value, options),
    [language]
  );

  return useMemo(
    () => ({
      t,
      tl,
      i18n,
      language,
      setLanguage,
      options,
    }),
    [i18n, language, options, setLanguage, t, tl],
  );
}
