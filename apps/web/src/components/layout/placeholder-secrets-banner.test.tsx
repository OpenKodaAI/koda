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
    expect(screen.getByRole("status")).toHaveTextContent("S3_ACCESS_KEY_ID ainda usam");
  });

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
