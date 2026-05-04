import { describe, expect, it } from "vitest";
import { SUPPORTED_LANGUAGES, translateLiteralForLanguage } from "@/lib/i18n";

const WARNING =
  "Extremamente recomendado escolher e baixar um modelo abaixo. Sem ele a recuperação semântica cai para um match por palavras-chave (qualidade degradada).";
const INTRO =
  "Escolha o modelo usado para memória, knowledge base e cache semântico. Nenhum vem pré-instalado: baixe sob demanda quando precisar.";
const DESCRIPTION =
  "Modelo balanceado e leve. Boa escolha como ponto de partida para memória e cache em PT-BR + EN. nDCG@5 ≈ 0.91 no bench interno.";

describe("embedding settings literal translations", () => {
  it("maps the missing embedding model warning in every supported language", () => {
    for (const language of SUPPORTED_LANGUAGES) {
      const translated = translateLiteralForLanguage(language, WARNING);
      expect(translated).toBeTruthy();
      if (language !== "pt-BR") {
        expect(translated).not.toBe(WARNING);
      }
    }
  });

  it("maps the embedding intro, hardware hints, and model descriptions", () => {
    for (const language of SUPPORTED_LANGUAGES) {
      const intro = translateLiteralForLanguage(language, INTRO);
      const description = translateLiteralForLanguage(language, DESCRIPTION);
      expect(intro).toBeTruthy();
      expect(description).toBeTruthy();
      if (language !== "pt-BR") {
        expect(intro).not.toBe(INTRO);
        expect(description).not.toBe(DESCRIPTION);
      }
      expect(translateLiteralForLanguage(language, "Apple Silicon recomendado")).toBeTruthy();
      expect(translateLiteralForLanguage(language, "GPU dedicada recomendada")).toBeTruthy();
    }
  });

  it("keeps Portuguese download wording explicit after generated literal overrides", () => {
    expect(translateLiteralForLanguage("pt-BR", "Baixando")).toBe("Baixando");
  });
});
