import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { McpServerEditorModal } from "./mcp-server-editor-modal";

vi.mock("@/hooks/use-app-i18n", () => ({
  useAppI18n: () => ({
    tl: (value: string) => value,
  }),
}));

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

    await user.type(screen.getByPlaceholderText("meu-servidor"), "filesystem");

    expect(
      screen.getByText("Este identificador e reservado e nao pode ser usado."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Adicionar servidor" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Adicionar servidor" }));
    expect(onSave).not.toHaveBeenCalled();
  });
});
