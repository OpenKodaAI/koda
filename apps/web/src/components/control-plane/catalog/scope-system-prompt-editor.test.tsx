import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ToastProvider } from "@/hooks/use-toast";
import { WorkspaceSpecEditor } from "./workspace-spec-editor";
import { SquadSpecEditor } from "./squad-spec-editor";

function renderWithProviders(node: React.ReactNode) {
  return render(
    <I18nProvider initialLanguage="pt-BR">
      <ToastProvider>{node}</ToastProvider>
    </I18nProvider>,
  );
}

describe("scope system prompt editors", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("loads and saves the workspace system prompt payload", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(globalThis.fetch);

    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            spec: {},
            documents: { system_prompt_md: "# Contexto\nWorkspace legado" },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ spec: {}, documents: {} }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );

    renderWithProviders(
      <WorkspaceSpecEditor
        workspaceId="workspace-product"
        workspaceName="Produto"
        open
        onClose={() => undefined}
      />,
    );

    const textarea = await screen.findByRole("textbox");
    await waitFor(() => {
      expect(textarea).toHaveValue("# Contexto\nWorkspace legado");
    });
    await user.clear(textarea);
    await user.type(textarea, "# Novo contexto");
    await user.click(screen.getByRole("button", { name: /Salvar system prompt/i }));

    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/control-plane/workspaces/workspace-product/spec",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          spec: {},
          documents: { system_prompt_md: "# Novo contexto" },
        }),
      }),
    );
  });

  it("loads and saves the squad system prompt payload", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(globalThis.fetch);

    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            spec: {},
            documents: { system_prompt_md: "# Playbook\nSquad plataforma" },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ spec: {}, documents: {} }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );

    renderWithProviders(
      <SquadSpecEditor
        workspaceId="workspace-product"
        squadId="squad-platform"
        squadName="Plataforma"
        open
        onClose={() => undefined}
      />,
    );

    const textarea = await screen.findByRole("textbox");
    await waitFor(() => {
      expect(textarea).toHaveValue("# Playbook\nSquad plataforma");
    });
    await user.clear(textarea);
    await user.type(textarea, "# Nova squad");
    await user.click(screen.getByRole("button", { name: /Salvar system prompt/i }));

    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/control-plane/workspaces/workspace-product/squads/squad-platform/spec",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          spec: {},
          documents: { system_prompt_md: "# Nova squad" },
        }),
      }),
    );
  });
});
