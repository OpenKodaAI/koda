import i18n, { type TOptions } from "i18next";
import { literalResources, resources } from "@/lib/i18n-resources";

export const DEFAULT_LANGUAGE = "en-US" as const;
export const LOCALE_COOKIE_KEY = "atlas.locale" as const;
export const SUPPORTED_LANGUAGES = ["en-US", "pt-BR", "es-ES"] as const;

export type AppLanguage = (typeof SUPPORTED_LANGUAGES)[number];
type TranslateOptions = Omit<TOptions, "context"> & { context?: string };
export type AppTranslator = (key: string, options?: Record<string, unknown>) => string;
let currentLanguageOverride: AppLanguage = DEFAULT_LANGUAGE;

const LITERAL_TERM_REPLACEMENTS: Partial<Record<AppLanguage, Array<[RegExp, string]>>> = {
  "pt-BR": [
    [/\bWorkspaces\b/g, "Espaços de trabalho"],
    [/\bWorkspace\b/g, "Espaço de trabalho"],
    [/\bworkspaces\b/g, "espaços de trabalho"],
    [/\bworkspace\b/g, "espaço de trabalho"],
    [/\bSquads\b/g, "Times"],
    [/\bSquad\b/g, "Time"],
    [/\bsquads\b/g, "times"],
    [/\bsquad\b/g, "time"],
    [/\bbot\(s\)\b/g, "bots"],
  ],
  "es-ES": [
    [/\bWorkspaces\b/g, "Espacios de trabajo"],
    [/\bWorkspace\b/g, "Espacio de trabajo"],
    [/\bworkspaces\b/g, "espacios de trabajo"],
    [/\bworkspace\b/g, "espacio de trabajo"],
    [/\bSquads\b/g, "Equipos"],
    [/\bSquad\b/g, "Equipo"],
    [/\bsquads\b/g, "equipos"],
    [/\bsquad\b/g, "equipo"],
    [/\bbot\(s\)\b/g, "bots"],
  ],
};

const LANGUAGE_ALIASES: Record<string, AppLanguage> = {
  en: "en-US",
  "en-us": "en-US",
  pt: "pt-BR",
  "pt-br": "pt-BR",
  es: "es-ES",
  "es-es": "es-ES",
};

export const LANGUAGE_OPTIONS: Array<{ value: AppLanguage; labelKey: string }> = [
  { value: "en-US", labelKey: "language.options.en-US" },
  { value: "pt-BR", labelKey: "language.options.pt-BR" },
  { value: "es-ES", labelKey: "language.options.es-ES" },
];

export function normalizeLanguage(value?: string | null): AppLanguage {
  if (!value) return DEFAULT_LANGUAGE;

  const normalized = value.trim().toLowerCase();
  return (
    LANGUAGE_ALIASES[normalized] ??
    (SUPPORTED_LANGUAGES.find((language) => language.toLowerCase() === normalized) ?? DEFAULT_LANGUAGE)
  );
}

export function getI18nInstance() {
  if (!i18n.isInitialized) {
    i18n.init({
      resources,
      lng: currentLanguageOverride,
      fallbackLng: DEFAULT_LANGUAGE,
      supportedLngs: [...SUPPORTED_LANGUAGES],
      interpolation: {
        escapeValue: false,
      },
      returnNull: false,
      defaultNS: "translation",
      initImmediate: false,
    });
  }

  return i18n;
}

export function setCurrentLanguage(language: string | null | undefined) {
  currentLanguageOverride = normalizeLanguage(language);
  return currentLanguageOverride;
}

export function getCurrentLanguage(): AppLanguage {
  return normalizeLanguage(currentLanguageOverride);
}

export function translate(key: string, options?: TranslateOptions) {
  const instance = getI18nInstance();
  const language = getCurrentLanguage();
  return (
    options === undefined
      ? instance.t(key, { lng: language })
      : instance.t(key, { ...options, lng: language })
  ) as string;
}

function getLiteralValue(language: AppLanguage, value: string): string | undefined {
  return literalResources[language]?.[value as keyof (typeof literalResources)[typeof language]] as string | undefined;
}

function applyLiteralTermReplacements(language: AppLanguage, value: string) {
  const replacements = LITERAL_TERM_REPLACEMENTS[language];
  if (!replacements?.length) return value;

  return replacements.reduce(
    (current, [pattern, replacement]) => current.replace(pattern, replacement),
    value,
  );
}

export function translateLiteral(value: string, options?: TranslateOptions) {
  const language = getCurrentLanguage();
  const translated = getLiteralValue(language, value);
  return applyLiteralTermReplacements(
    language,
    interpolateTemplate(translated ?? value, options),
  );
}

function getResourceValue(language: AppLanguage, key: string): unknown {
  return key.split(".").reduce<unknown>((current, segment) => {
    if (typeof current !== "object" || current === null) return undefined;
    return (current as Record<string, unknown>)[segment];
  }, resources[language]?.translation);
}

function interpolateTemplate(template: string, options?: TranslateOptions) {
  if (!options) return template;

  return template.replace(/\{\{(\w+)\}\}/g, (_, token: string) => {
    const value = options[token as keyof TranslateOptions];
    return value == null ? "" : String(value);
  });
}

export function translateForLanguage(
  language: string | null | undefined,
  key: string,
  options?: TranslateOptions
) {
  const normalized = normalizeLanguage(language);
  const value = getResourceValue(normalized, key);
  if (typeof value === "string") {
    return interpolateTemplate(value, options);
  }
  if (typeof options?.defaultValue === "string") {
    return interpolateTemplate(options.defaultValue, options);
  }
  return key;
}

export function translateLiteralForLanguage(
  language: string | null | undefined,
  value: string,
  options?: TranslateOptions,
) {
  const normalized = normalizeLanguage(language);
  return applyLiteralTermReplacements(
    normalized,
    interpolateTemplate(getLiteralValue(normalized, value) ?? value, options),
  );
}
