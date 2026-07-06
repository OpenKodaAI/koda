import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { McpServerEditorModal } from "./mcp-server-editor-modal";

vi.mock("@/hooks/use-app-i18n", async () => {
  const { translateForLanguage } = await vi.importActual<typeof import("@/lib/i18n")>("@/lib/i18n");
  const t = (key: string, options?: Record<string, unknown>) => translateForLanguage("pt-BR", key, options);

  return {
    useAppI18n: () => ({
      t,
      tl: (value: string) => value,
      i18n: { t },
      language: "pt-BR",
      setLanguage: vi.fn(),
      options: [],
    }),
  };
});

describe("McpServerEditorModal", () => {
  it("blocks reserved server keys from being saved", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);

    render(
      <McpServerEditorModal
        server={null}
        mode="create"
        onClose={vi.fn()}
        onSave={onSave}
      />,
    );

    await user.type(screen.getByPlaceholderText("my-server"), "filesystem");

    expect(
      screen.getByText("Este identificador é reservado e não pode ser usado."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Adicionar servidor" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Adicionar servidor" }));
    expect(onSave).not.toHaveBeenCalled();
  });
});
