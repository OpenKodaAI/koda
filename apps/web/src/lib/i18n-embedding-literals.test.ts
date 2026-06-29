import { describe, expect, it } from "vitest";
import { SUPPORTED_LANGUAGES, translateLiteralForLanguage } from "@/lib/i18n";

const WARNING =
  "Extremamente recomendado escolher e baixar um modelo abaixo. Sem ele a recuperação semântica cai para um match por palavras-chave (qualidade degradada).";
const INTRO =
  "Escolha o modelo usado para memória, knowledge base e cache semântico. Nenhum vem pré-instalado: baixe sob demanda quando precisar.";
const FIELD_DESCRIPTION =
  "O modelo usado para indexar memórias, knowledge base e cache semântico. Nenhum modelo vem instalado: baixe sob demanda apenas se precisar.";
const DESCRIPTION =
  "Modelo balanceado e leve. Boa escolha como ponto de partida para memória e cache em PT-BR + EN. nDCG@5 ≈ 0.91 no bench interno.";
const UI_LITERALS = [
  "Modelo de embedding",
  FIELD_DESCRIPTION,
  "Não foi possível carregar o catálogo",
  "Tentar novamente",
  "Carregando catálogo de modelos...",
  "Modelo baixado e pronto para uso",
  "Falha ao selecionar modelo",
  "Modelo ativo",
  "Falha ao apagar modelo",
  "Modelo apagado",
  "Ativo",
  "Baixando...",
  "Em uso",
  "Usar este",
  "Confirmar — clique novamente para apagar",
  "Apagar modelo",
  "Confirmar",
  "multi",
  "EN",
];

const EXPECTED_UI_TRANSLATIONS: Record<string, Record<string, string>> = {
  "en-US": {
    "Modelo de embedding": "Embedding model",
    [FIELD_DESCRIPTION]:
      "The model used to index memories, the knowledge base, and semantic cache. No model is installed by default: download one on demand only if needed.",
    "Não foi possível carregar o catálogo": "Could not load the catalog",
    "Tentar novamente": "Try again",
    "Carregando catálogo de modelos...": "Loading model catalog...",
    "Modelo baixado e pronto para uso": "Model downloaded and ready to use",
    "Falha ao selecionar modelo": "Failed to select model",
    "Modelo ativo": "Active model",
    "Falha ao apagar modelo": "Failed to delete model",
    "Modelo apagado": "Model deleted",
    "Ativo": "Active",
    "Baixando...": "Downloading...",
    "Em uso": "In use",
    "Usar este": "Use this",
    "Confirmar — clique novamente para apagar": "Confirm — click again to delete",
    "Apagar modelo": "Delete model",
    "Confirmar": "Confirm",
    multi: "multi",
    EN: "EN",
  },
  "pt-BR": {
    "Modelo de embedding": "Modelo de embedding",
    [FIELD_DESCRIPTION]: FIELD_DESCRIPTION,
    "Não foi possível carregar o catálogo": "Não foi possível carregar o catálogo",
    "Tentar novamente": "Tentar novamente",
    "Carregando catálogo de modelos...": "Carregando catálogo de modelos...",
    "Modelo baixado e pronto para uso": "Modelo baixado e pronto para uso",
    "Falha ao selecionar modelo": "Falha ao selecionar modelo",
    "Modelo ativo": "Modelo ativo",
    "Falha ao apagar modelo": "Falha ao apagar modelo",
    "Modelo apagado": "Modelo apagado",
    "Ativo": "Ativo",
    "Baixando...": "Baixando...",
    "Em uso": "Em uso",
    "Usar este": "Usar este",
    "Confirmar — clique novamente para apagar": "Confirmar — clique novamente para apagar",
    "Apagar modelo": "Apagar modelo",
    "Confirmar": "Confirmar",
    multi: "multi",
    EN: "EN",
  },
  "es-ES": {
    "Modelo de embedding": "Modelo de embeddings",
    [FIELD_DESCRIPTION]:
      "El modelo usado para indexar memorias, knowledge base y caché semántica. Ningún modelo viene instalado: descárgalo bajo demanda solo si lo necesitas.",
    "Não foi possível carregar o catálogo": "No se pudo cargar el catálogo",
    "Tentar novamente": "Intentar de nuevo",
    "Carregando catálogo de modelos...": "Cargando catálogo de modelos...",
    "Modelo baixado e pronto para uso": "Modelo descargado y listo para usar",
    "Falha ao selecionar modelo": "Error al seleccionar el modelo",
    "Modelo ativo": "Modelo activo",
    "Falha ao apagar modelo": "Error al borrar el modelo",
    "Modelo apagado": "Modelo borrado",
    "Ativo": "Activo",
    "Baixando...": "Descargando...",
    "Em uso": "En uso",
    "Usar este": "Usar este",
    "Confirmar — clique novamente para apagar": "Confirmar — haz clic de nuevo para borrar",
    "Apagar modelo": "Borrar modelo",
    "Confirmar": "Confirmar",
    multi: "multi",
    EN: "EN",
  },
  "fr-FR": {
    "Modelo de embedding": "Modèle d'embedding",
    [FIELD_DESCRIPTION]:
      "Le modèle utilisé pour indexer les mémoires, la base de connaissances et le cache sémantique. Aucun modèle n'est installé : téléchargez-en un à la demande seulement si nécessaire.",
    "Não foi possível carregar o catálogo": "Impossible de charger le catalogue",
    "Tentar novamente": "Réessayer",
    "Carregando catálogo de modelos...": "Chargement du catalogue de modèles...",
    "Modelo baixado e pronto para uso": "Modèle téléchargé et prêt à l'emploi",
    "Falha ao selecionar modelo": "Échec de la sélection du modèle",
    "Modelo ativo": "Modèle actif",
    "Falha ao apagar modelo": "Échec de la suppression du modèle",
    "Modelo apagado": "Modèle supprimé",
    "Ativo": "Actif",
    "Baixando...": "Téléchargement...",
    "Em uso": "En cours d'utilisation",
    "Usar este": "Utiliser celui-ci",
    "Confirmar — clique novamente para apagar": "Confirmer — cliquez à nouveau pour supprimer",
    "Apagar modelo": "Supprimer le modèle",
    "Confirmar": "Confirmer",
    multi: "multi",
    EN: "EN",
  },
  "de-DE": {
    "Modelo de embedding": "Embedding-Modell",
    [FIELD_DESCRIPTION]:
      "Das Modell zum Indexieren von Erinnerungen, Knowledge Base und semantischem Cache. Kein Modell ist installiert: lade nur bei Bedarf eines herunter.",
    "Não foi possível carregar o catálogo": "Katalog konnte nicht geladen werden",
    "Tentar novamente": "Erneut versuchen",
    "Carregando catálogo de modelos...": "Modellkatalog wird geladen...",
    "Modelo baixado e pronto para uso": "Modell heruntergeladen und einsatzbereit",
    "Falha ao selecionar modelo": "Modell konnte nicht ausgewählt werden",
    "Modelo ativo": "Aktives Modell",
    "Falha ao apagar modelo": "Modell konnte nicht gelöscht werden",
    "Modelo apagado": "Modell gelöscht",
    "Ativo": "Aktiv",
    "Baixando...": "Wird heruntergeladen...",
    "Em uso": "In Verwendung",
    "Usar este": "Dieses verwenden",
    "Confirmar — clique novamente para apagar": "Bestätigen — zum Löschen erneut klicken",
    "Apagar modelo": "Modell löschen",
    "Confirmar": "Bestätigen",
    multi: "multi",
    EN: "EN",
  },
};

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

  it("maps the embedding field and picker controls in every supported language", () => {
    for (const language of SUPPORTED_LANGUAGES) {
      for (const literal of UI_LITERALS) {
        expect(translateLiteralForLanguage(language, literal)).toBe(
          EXPECTED_UI_TRANSLATIONS[language][literal],
        );
      }
    }
  });

  it("keeps Portuguese download wording explicit after generated literal overrides", () => {
    expect(translateLiteralForLanguage("pt-BR", "Baixando")).toBe("Baixando");
    expect(translateLiteralForLanguage("pt-BR", "Baixando...")).toBe("Baixando...");
  });
});
