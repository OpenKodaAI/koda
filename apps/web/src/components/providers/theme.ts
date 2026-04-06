export type ThemePreference = "system" | "light" | "dark";
export type Theme = "light" | "dark";

export const DEFAULT_THEME_PREFERENCE: ThemePreference = "system";

export function normalizeThemePreference(value?: string | null): ThemePreference {
  const normalized = value?.trim().toLowerCase();

  if (normalized === "light" || normalized === "dark" || normalized === "system") {
    return normalized;
  }

  return DEFAULT_THEME_PREFERENCE;
}

export function resolveThemePreference(
  preference: ThemePreference,
  systemTheme: Theme,
): Theme {
  return preference === "system" ? systemTheme : preference;
}

export function applyThemeToDocumentRoot(
  root: HTMLElement,
  preference: ThemePreference,
  theme: Theme,
) {
  root.dataset.themePreference = preference;
  root.dataset.theme = theme;
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
}

function escapeScriptValue(value: string) {
  return JSON.stringify(value);
}

export function buildThemeBootstrapScript({
  storageKey,
  cookieKey,
  fallbackPreference = DEFAULT_THEME_PREFERENCE,
}: {
  storageKey: string;
  cookieKey: string;
  fallbackPreference?: ThemePreference;
}) {
  const storageKeyLiteral = escapeScriptValue(storageKey);
  const cookieKeyLiteral = escapeScriptValue(cookieKey);
  const fallbackPreferenceLiteral = escapeScriptValue(fallbackPreference);

  return `
(function () {
  var storageKey = ${storageKeyLiteral};
  var cookieKey = ${cookieKeyLiteral};
  var fallbackPreference = ${fallbackPreferenceLiteral};
  var root = document.documentElement;

  function isThemePreference(value) {
    return value === "system" || value === "light" || value === "dark";
  }

  function readCookie(name) {
    var cookieName = name + "=";
    var entries = document.cookie ? document.cookie.split("; ") : [];

    for (var index = 0; index < entries.length; index += 1) {
      var entry = entries[index];

      if (entry.indexOf(cookieName) === 0) {
        return decodeURIComponent(entry.slice(cookieName.length));
      }
    }

    return null;
  }

  function getSystemTheme() {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return "light";
    }

    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function readPreference() {
    try {
      var rawPreference = window.localStorage.getItem(storageKey);

      if (rawPreference) {
        var parsedPreference = JSON.parse(rawPreference);

        if (isThemePreference(parsedPreference)) {
          return parsedPreference;
        }
      }
    } catch (error) {
      // Best effort.
    }

    var cookiePreference = readCookie(cookieKey);

    if (isThemePreference(cookiePreference)) {
      return cookiePreference;
    }

    return fallbackPreference;
  }

  var preference = readPreference();
  var theme = preference === "system" ? getSystemTheme() : preference;

  root.dataset.themePreference = preference;
  root.dataset.theme = theme;
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
})();
`.trim();
}
