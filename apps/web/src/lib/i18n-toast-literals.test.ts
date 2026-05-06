import { describe, expect, it } from "vitest";
import { SUPPORTED_LANGUAGES, translateLiteralForLanguage } from "@/lib/i18n";

const TOAST_LITERALS = [
  "Fechar aviso",
  "Cancelando download…",
  "Cancelando",
  "Cancelando download",
  "Download concluído antes do cancelamento.",
  "Falha no download",
  "Download cancelado.",
  "Falha ao cancelar o download",
  "Cancelar",
  "Cancelar download",
  "Sem resposta do servidor — verifique a conexão",
  "Conexão instável — tentando reconectar",
  "Falha ao iniciar o download",
  "Retomando download…",
  "No module named 'huggingface_hub'",
  "Baixando modelo Kokoro",
  "Modelo Kokoro pronto.",
  "Baixando voz Kokoro · {{voice}}",
  'Voz "{{voice}}" disponível.',
  "Baixando {{label}}",
  "{{label}} pronto.",
];

const EXPECTED_TOAST_TRANSLATIONS: Record<string, Record<string, string>> = {
  "en-US": {
    "Fechar aviso": "Dismiss notification",
    "Cancelando download…": "Cancelling download...",
    "Cancelando": "Cancelling",
    "Cancelando download": "Cancelling download",
    "Download concluído antes do cancelamento.": "Download completed before cancellation.",
    "Falha no download": "Download failed",
    "Download cancelado.": "Download canceled.",
    "Falha ao cancelar o download": "Failed to cancel the download",
    "Cancelar": "Cancel",
    "Cancelar download": "Cancel download",
    "Sem resposta do servidor — verifique a conexão": "No response from the server — check the connection",
    "Conexão instável — tentando reconectar": "Unstable connection — trying to reconnect",
    "Falha ao iniciar o download": "Failed to start the download",
    "Retomando download…": "Resuming download...",
    "No module named 'huggingface_hub'":
      "Required package huggingface_hub is missing. Reinstall the project dependencies and try again.",
    "Baixando modelo Kokoro": "Downloading Kokoro model",
    "Modelo Kokoro pronto.": "Kokoro model ready.",
    "Baixando voz Kokoro · {{voice}}": "Downloading Kokoro voice · {{voice}}",
    'Voz "{{voice}}" disponível.': 'Voice "{{voice}}" available.',
    "Baixando {{label}}": "Downloading {{label}}",
    "{{label}} pronto.": "{{label}} ready.",
  },
  "pt-BR": {
    "Fechar aviso": "Fechar aviso",
    "Cancelando download…": "Cancelando download...",
    "Cancelando": "Cancelando",
    "Cancelando download": "Cancelando download",
    "Download concluído antes do cancelamento.": "Download concluído antes do cancelamento.",
    "Falha no download": "Falha no download",
    "Download cancelado.": "Download cancelado.",
    "Falha ao cancelar o download": "Falha ao cancelar o download",
    "Cancelar": "Cancelar",
    "Cancelar download": "Cancelar download",
    "Sem resposta do servidor — verifique a conexão": "Sem resposta do servidor — verifique a conexão",
    "Conexão instável — tentando reconectar": "Conexão instável — tentando reconectar",
    "Falha ao iniciar o download": "Falha ao iniciar o download",
    "Retomando download…": "Retomando download...",
    "No module named 'huggingface_hub'":
      "Dependência huggingface_hub ausente. Reinstale as dependências do projeto e tente novamente.",
    "Baixando modelo Kokoro": "Baixando modelo Kokoro",
    "Modelo Kokoro pronto.": "Modelo Kokoro pronto.",
    "Baixando voz Kokoro · {{voice}}": "Baixando voz Kokoro · {{voice}}",
    'Voz "{{voice}}" disponível.': 'Voz "{{voice}}" disponível.',
    "Baixando {{label}}": "Baixando {{label}}",
    "{{label}} pronto.": "{{label}} pronto.",
  },
  "es-ES": {
    "Fechar aviso": "Cerrar aviso",
    "Cancelando download…": "Cancelando descarga...",
    "Cancelando": "Cancelando",
    "Cancelando download": "Cancelando descarga",
    "Download concluído antes do cancelamento.": "La descarga se completó antes de la cancelación.",
    "Falha no download": "Error en la descarga",
    "Download cancelado.": "Descarga cancelada.",
    "Falha ao cancelar o download": "No se pudo cancelar la descarga",
    "Cancelar": "Cancelar",
    "Cancelar download": "Cancelar descarga",
    "Sem resposta do servidor — verifique a conexão": "Sin respuesta del servidor — verifica la conexión",
    "Conexão instável — tentando reconectar": "Conexión inestable — intentando reconectar",
    "Falha ao iniciar o download": "No se pudo iniciar la descarga",
    "Retomando download…": "Reanudando descarga...",
    "No module named 'huggingface_hub'":
      "Falta el paquete requerido huggingface_hub. Reinstala las dependencias del proyecto e inténtalo de nuevo.",
    "Baixando modelo Kokoro": "Descargando modelo Kokoro",
    "Modelo Kokoro pronto.": "Modelo Kokoro listo.",
    "Baixando voz Kokoro · {{voice}}": "Descargando voz Kokoro · {{voice}}",
    'Voz "{{voice}}" disponível.': 'Voz "{{voice}}" disponible.',
    "Baixando {{label}}": "Descargando {{label}}",
    "{{label}} pronto.": "{{label}} listo.",
  },
  "fr-FR": {
    "Fechar aviso": "Fermer l'avis",
    "Cancelando download…": "Annulation du téléchargement...",
    "Cancelando": "Annulation",
    "Cancelando download": "Annulation du téléchargement",
    "Download concluído antes do cancelamento.": "Téléchargement terminé avant l'annulation.",
    "Falha no download": "Échec du téléchargement",
    "Download cancelado.": "Téléchargement annulé.",
    "Falha ao cancelar o download": "Échec de l'annulation du téléchargement",
    "Cancelar": "Annuler",
    "Cancelar download": "Annuler le téléchargement",
    "Sem resposta do servidor — verifique a conexão": "Pas de réponse du serveur — vérifiez la connexion",
    "Conexão instável — tentando reconectar": "Connexion instable — tentative de reconnexion",
    "Falha ao iniciar o download": "Échec du démarrage du téléchargement",
    "Retomando download…": "Reprise du téléchargement...",
    "No module named 'huggingface_hub'":
      "Le paquet requis huggingface_hub est absent. Réinstallez les dépendances du projet puis réessayez.",
    "Baixando modelo Kokoro": "Téléchargement du modèle Kokoro",
    "Modelo Kokoro pronto.": "Modèle Kokoro prêt.",
    "Baixando voz Kokoro · {{voice}}": "Téléchargement de la voix Kokoro · {{voice}}",
    'Voz "{{voice}}" disponível.': 'Voix "{{voice}}" disponible.',
    "Baixando {{label}}": "Téléchargement de {{label}}",
    "{{label}} pronto.": "{{label}} prêt.",
  },
  "de-DE": {
    "Fechar aviso": "Hinweis schließen",
    "Cancelando download…": "Download wird abgebrochen...",
    "Cancelando": "Abbrechen läuft",
    "Cancelando download": "Download abbrechen",
    "Download concluído antes do cancelamento.": "Download wurde vor dem Abbruch abgeschlossen.",
    "Falha no download": "Download fehlgeschlagen",
    "Download cancelado.": "Download abgebrochen.",
    "Falha ao cancelar o download": "Download konnte nicht abgebrochen werden",
    "Cancelar": "Abbrechen",
    "Cancelar download": "Download abbrechen",
    "Sem resposta do servidor — verifique a conexão": "Keine Antwort vom Server — Verbindung prüfen",
    "Conexão instável — tentando reconectar": "Instabile Verbindung — erneuter Verbindungsversuch",
    "Falha ao iniciar o download": "Download konnte nicht gestartet werden",
    "Retomando download…": "Download wird fortgesetzt...",
    "No module named 'huggingface_hub'":
      "Das erforderliche Paket huggingface_hub fehlt. Installiere die Projektabhängigkeiten erneut und versuche es noch einmal.",
    "Baixando modelo Kokoro": "Kokoro-Modell wird heruntergeladen",
    "Modelo Kokoro pronto.": "Kokoro-Modell bereit.",
    "Baixando voz Kokoro · {{voice}}": "Kokoro-Stimme wird heruntergeladen · {{voice}}",
    'Voz "{{voice}}" disponível.': 'Stimme "{{voice}}" verfügbar.',
    "Baixando {{label}}": "{{label}} wird heruntergeladen",
    "{{label}} pronto.": "{{label}} bereit.",
  },
};

describe("toast literal translations", () => {
  it("maps fixed toast copy in every supported language", () => {
    for (const language of SUPPORTED_LANGUAGES) {
      for (const literal of TOAST_LITERALS) {
        expect(translateLiteralForLanguage(language, literal)).toBe(
          EXPECTED_TOAST_TRANSLATIONS[language][literal],
        );
      }
    }
  });

  it("interpolates translated download toast templates", () => {
    expect(
      translateLiteralForLanguage("de-DE", "Baixando {{label}}", { label: "MiniLM" }),
    ).toBe("MiniLM wird heruntergeladen");
    expect(
      translateLiteralForLanguage("fr-FR", 'Voz "{{voice}}" disponível.', {
        voice: "Bella",
      }),
    ).toBe('Voix "Bella" disponible.');
  });
});
