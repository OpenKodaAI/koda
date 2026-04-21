import i18n, { type InitOptions, type TOptions } from "i18next";
import { literalResources, resources } from "@/lib/i18n-resources";

export const DEFAULT_LANGUAGE = "en-US" as const;
export const LOCALE_COOKIE_KEY = "atlas.locale" as const;
export const SUPPORTED_LANGUAGES = ["en-US", "pt-BR", "es-ES", "fr-FR", "de-DE"] as const;

export type AppLanguage = (typeof SUPPORTED_LANGUAGES)[number];
type TranslateOptions = Omit<TOptions, "context"> & { context?: string };
export type AppTranslator = (key: string, options?: Record<string, unknown>) => string;
let currentLanguageOverride: AppLanguage = DEFAULT_LANGUAGE;

const LITERAL_TERM_REPLACEMENTS: Partial<Record<AppLanguage, Array<[RegExp, string]>>> = {
  "en-US": [
    [/\bbot\(s\)\b/g, "agent(s)"],
    [/\bBots\b/g, "Agents"],
    [/\bbots\b/g, "agents"],
    [/\bBot\b/g, "Agent"],
    [/\bbot\b/g, "agent"],
  ],
  "pt-BR": [
    [/\bWorkspaces\b/g, "Espaços de trabalho"],
    [/\bWorkspace\b/g, "Espaço de trabalho"],
    [/\bworkspaces\b/g, "espaços de trabalho"],
    [/\bworkspace\b/g, "espaço de trabalho"],
    [/\bSquads\b/g, "Times"],
    [/\bSquad\b/g, "Time"],
    [/\bsquads\b/g, "times"],
    [/\bsquad\b/g, "time"],
    [/\bbot\(s\)\b/g, "agente(s)"],
    [/\bBots\b/g, "Agentes"],
    [/\bbots\b/g, "agentes"],
    [/\bBot\b/g, "Agente"],
    [/\bbot\b/g, "agente"],
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
    [/\bbot\(s\)\b/g, "agente(s)"],
    [/\bBots\b/g, "Agentes"],
    [/\bbots\b/g, "agentes"],
    [/\bBot\b/g, "Agente"],
    [/\bbot\b/g, "agente"],
  ],
  "fr-FR": [
    [/\bWorkspaces\b/g, "Espaces de travail"],
    [/\bWorkspace\b/g, "Espace de travail"],
    [/\bworkspaces\b/g, "espaces de travail"],
    [/\bworkspace\b/g, "espace de travail"],
    [/\bSquads\b/g, "Escouades"],
    [/\bSquad\b/g, "Escouade"],
    [/\bsquads\b/g, "escouades"],
    [/\bsquad\b/g, "escouade"],
    [/\bbot\(s\)\b/g, "agent(s)"],
    [/\bBots\b/g, "Agents"],
    [/\bbots\b/g, "agents"],
    [/\bBot\b/g, "Agent"],
    [/\bbot\b/g, "agent"],
  ],
  "de-DE": [
    [/\bWorkspaces\b/g, "Arbeitsbereiche"],
    [/\bWorkspace\b/g, "Arbeitsbereich"],
    [/\bworkspaces\b/g, "Arbeitsbereiche"],
    [/\bworkspace\b/g, "Arbeitsbereich"],
    [/\bSquads\b/g, "Squads"],
    [/\bSquad\b/g, "Squad"],
    [/\bsquads\b/g, "Squads"],
    [/\bsquad\b/g, "Squad"],
    [/\bbot\(s\)\b/g, "Agent(en)"],
    [/\bBots\b/g, "Agenten"],
    [/\bbots\b/g, "Agenten"],
    [/\bBot\b/g, "Agent"],
    [/\bbot\b/g, "Agent"],
  ],
};

const LANGUAGE_ALIASES: Record<string, AppLanguage> = {
  en: "en-US",
  "en-us": "en-US",
  pt: "pt-BR",
  "pt-br": "pt-BR",
  es: "es-ES",
  "es-es": "es-ES",
  fr: "fr-FR",
  "fr-fr": "fr-FR",
  de: "de-DE",
  "de-de": "de-DE",
};

export const LANGUAGE_OPTIONS: Array<{ value: AppLanguage; labelKey: string }> = [
  { value: "en-US", labelKey: "language.options.en-US" },
  { value: "pt-BR", labelKey: "language.options.pt-BR" },
  { value: "es-ES", labelKey: "language.options.es-ES" },
  { value: "fr-FR", labelKey: "language.options.fr-FR" },
  { value: "de-DE", labelKey: "language.options.de-DE" },
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
    const initOptions = {
      resources,
      lng: currentLanguageOverride,
      fallbackLng: DEFAULT_LANGUAGE,
      supportedLngs: [...SUPPORTED_LANGUAGES],
      interpolation: {
        escapeValue: false,
      },
      returnNull: false,
      defaultNS: "translation",
      initAsync: false,
    } satisfies InitOptions;

    i18n.init(initOptions);
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
  const value = (
    options === undefined
      ? instance.t(key, { lng: language })
      : instance.t(key, { ...options, lng: language })
  ) as string;
  return applyLiteralTermReplacements(language, value);
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
    return applyLiteralTermReplacements(normalized, interpolateTemplate(value, options));
  }
  if (normalized !== DEFAULT_LANGUAGE) {
    const fallback = getResourceValue(DEFAULT_LANGUAGE, key);
    if (typeof fallback === "string") {
      return applyLiteralTermReplacements(normalized, interpolateTemplate(fallback, options));
    }
  }
  if (typeof options?.defaultValue === "string") {
    return applyLiteralTermReplacements(normalized, interpolateTemplate(options.defaultValue, options));
  }
  return key;
}

export function translateLiteralForLanguage(
  language: string | null | undefined,
  value: string,
  options?: TranslateOptions,
) {
  const normalized = normalizeLanguage(language);
  const native = getLiteralValue(normalized, value);
  const fallback =
    native === undefined && normalized !== DEFAULT_LANGUAGE
      ? getLiteralValue(DEFAULT_LANGUAGE, value)
      : undefined;
  return applyLiteralTermReplacements(
    normalized,
    interpolateTemplate(native ?? fallback ?? value, options),
  );
}
