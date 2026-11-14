import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  PLACEHOLDER_SECRETS_PATH,
  PlaceholderSecretsBanner,
} from "@/components/layout/placeholder-secrets-banner";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { LOCALE_COOKIE_KEY } from "@/lib/i18n";

const ROTATION_URL =
  "https://github.com/OpenKodaAI/koda/blob/main/docs/install/local.md#rotating-placeholder-postgres-and-object-storage-secrets";

const authMock = vi.hoisted(() => ({
  value: { isAuthenticated: true } as { isAuthenticated: boolean } | null,
}));

vi.mock("@/components/providers/auth-provider", () => ({
  useOptionalAuth: () => authMock.value,
}));

function installFetch(body: unknown, status = 200) {
  const fetchMock = vi.fn(
    async () =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderBanner(language = "en-US") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider initialLanguage={language}>
        <PlaceholderSecretsBanner />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  authMock.value = { isAuthenticated: true };
  // I18nProvider prefers a persisted locale over `initialLanguage`.
  window.localStorage.clear();
  document.cookie = `${LOCALE_COOKIE_KEY}=; path=/; max-age=0`;
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("PlaceholderSecretsBanner", () => {
  it("names the placeholder secrets and links to the rotation steps", async () => {
    const fetchMock = installFetch({
      placeholder_keys: ["POSTGRES_PASSWORD", "S3_SECRET_ACCESS_KEY"],
      rotation_url: ROTATION_URL,
    });

    renderBanner();

    expect(
      await screen.findByText("Database and object-storage secrets are still placeholders"),
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "POSTGRES_PASSWORD, S3_SECRET_ACCESS_KEY still use the public example values",
    );
    const link = screen.getByRole("link", { name: "Rotation steps" });
    expect(link).toHaveAttribute("href", ROTATION_URL);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(fetchMock).toHaveBeenCalledWith(
      PLACEHOLDER_SECRETS_PATH,
      expect.objectContaining({ credentials: "same-origin", cache: "no-store" }),
    );
  });

  it("renders in Portuguese too", async () => {
    installFetch({ placeholder_keys: ["S3_ACCESS_KEY_ID"], rotation_url: ROTATION_URL });

    renderBanner("pt-BR");

    expect(await screen.findByRole("link", { name: "Passos de rotação" })).toHaveAttribute(
      "href",
      ROTATION_URL,
    );
    expect(screen.getByRole("status")).toHaveTextContent("S3_ACCESS_KEY_ID ainda usa o valor");
  });

  // One key reads in the singular and several in the plural, in every locale (D-233).
  it.each([
    [
      "en-US",
      "A database or object-storage secret is still a placeholder",
      "POSTGRES_PASSWORD still uses the public example value from .env.example",
      "Database and object-storage secrets are still placeholders",
      "POSTGRES_PASSWORD, S3_SECRET_ACCESS_KEY still use the public example values from .env.example",
    ],
    [
      "pt-BR",
      "Um segredo do banco de dados ou do armazenamento de objetos ainda é um placeholder",
      "POSTGRES_PASSWORD ainda usa o valor público de exemplo do .env.example",
      "Os segredos do banco de dados e do armazenamento de objetos ainda são placeholders",
      "POSTGRES_PASSWORD, S3_SECRET_ACCESS_KEY ainda usam os valores públicos de exemplo do .env.example",
    ],
    [
      "es-ES",
      "Un secreto de la base de datos o del almacenamiento de objetos sigue siendo un marcador de posición",
      "POSTGRES_PASSWORD sigue usando el valor público de ejemplo de .env.example",
      "Los secretos de la base de datos y del almacenamiento de objetos siguen siendo marcadores de posición",
      "POSTGRES_PASSWORD, S3_SECRET_ACCESS_KEY siguen usando los valores públicos de ejemplo de .env.example",
    ],
    [
      "fr-FR",
      "Un secret de la base de données ou du stockage objet est encore une valeur d'exemple",
      "POSTGRES_PASSWORD utilise encore la valeur d'exemple publique de .env.example",
      "Les secrets de la base de données et du stockage objet sont encore des valeurs d'exemple",
      "POSTGRES_PASSWORD, S3_SECRET_ACCESS_KEY utilisent encore les valeurs d'exemple publiques de .env.example",
    ],
    [
      "de-DE",
      "Ein Datenbank- oder Objektspeicher-Geheimnis ist noch ein Platzhalter",
      "POSTGRES_PASSWORD verwendet noch den öffentlichen Beispielwert aus .env.example",
      "Datenbank- und Objektspeicher-Geheimnisse sind noch Platzhalter",
      "POSTGRES_PASSWORD, S3_SECRET_ACCESS_KEY verwenden noch die öffentlichen Beispielwerte aus .env.example",
    ],
  ])(
    "agrees with the number of keys in %s",
    async (language, oneTitle, oneDescription, severalTitle, severalDescription) => {
      installFetch({ placeholder_keys: ["POSTGRES_PASSWORD"], rotation_url: ROTATION_URL });
      const single = renderBanner(language);
      expect(await screen.findByText(oneTitle)).toBeInTheDocument();
      expect(screen.getByRole("status")).toHaveTextContent(oneDescription);
      expect(screen.getByRole("status")).not.toHaveTextContent(severalTitle);
      single.unmount();

      installFetch({
        placeholder_keys: ["POSTGRES_PASSWORD", "S3_SECRET_ACCESS_KEY"],
        rotation_url: ROTATION_URL,
      });
      renderBanner(language);
      expect(await screen.findByText(severalTitle)).toBeInTheDocument();
      expect(screen.getByRole("status")).toHaveTextContent(severalDescription);
      expect(screen.getByRole("status")).not.toHaveTextContent(oneTitle);
    },
  );

  it("stays hidden when every storage secret is real", async () => {
    const fetchMock = installFetch({ placeholder_keys: [], rotation_url: ROTATION_URL });

    renderBanner();

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("never asks for the signal without an operator session", async () => {
    authMock.value = { isAuthenticated: false };
    const fetchMock = installFetch({
      placeholder_keys: ["POSTGRES_PASSWORD"],
      rotation_url: ROTATION_URL,
    });

    renderBanner();

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it.each([
    ["an unauthenticated response", { error: "Operator session is required." }, 401],
    [
      "a non-https rotation link",
      { placeholder_keys: ["POSTGRES_PASSWORD"], rotation_url: "javascript:alert(1)" },
      200,
    ],
    [
      "something that is not a key name",
      { placeholder_keys: ["replace-with-a-random-postgres-password"], rotation_url: ROTATION_URL },
      200,
    ],
  ])("stays hidden on %s", async (_label, body, status) => {
    const fetchMock = installFetch(body, status);

    renderBanner();

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
