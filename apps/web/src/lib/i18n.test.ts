import { beforeEach, describe, expect, it, vi } from "vitest";

describe("i18n initialization", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("initializes synchronously and keeps translations available by language", async () => {
    const { getI18nInstance, setCurrentLanguage, translate, translateForLanguage } = await import("@/lib/i18n");

    const instance = getI18nInstance();

    expect(instance.isInitialized).toBe(true);

    setCurrentLanguage("pt-br");

    expect(translate("theme.options.dark")).toBe("Escuro");
    expect(translateForLanguage("es-es", "theme.options.dark")).toBe("Oscuro");
  });
});
