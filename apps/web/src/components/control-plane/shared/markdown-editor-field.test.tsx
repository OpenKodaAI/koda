import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { MarkdownEditorField } from "@/components/control-plane/shared/markdown-editor-field";

vi.mock("@/hooks/use-app-i18n", () => ({
  useAppI18n: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      typeof options?.defaultValue === "string" ? options.defaultValue : key,
    tl: (value: string) => value,
    i18n: {
      t: (key: string, options?: Record<string, unknown>) =>
        typeof options?.defaultValue === "string" ? options.defaultValue : key,
    },
    language: "en-US",
    setLanguage: vi.fn(),
    options: [],
  }),
}));

describe("MarkdownEditorField", () => {
  beforeEach(() => {
    Object.defineProperty(globalThis.navigator, "clipboard", {
      value: {
        writeText: async () => undefined,
        readText: async () => "# Conteudo colado",
      },
      configurable: true,
    });
  });

  it("defaults to edit mode and toggles to preview", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(
      <MarkdownEditorField
        label="Instructions"
        value="# Heading"
        onChange={onChange}
      />,
    );

    const editButton = screen.getByText("Editar").closest("button");
    const previewButton = screen.getByText("Preview").closest("button");
    expect(editButton).toHaveAttribute("aria-pressed", "true");
    expect(previewButton).toHaveAttribute("aria-pressed", "false");

    const textbox = screen.getByRole("textbox");
    expect(textbox).toBeInTheDocument();

    await user.type(textbox, " atualizado");
    expect(onChange).toHaveBeenCalled();

    if (!previewButton) throw new Error("Preview button not found");
    await user.click(previewButton);
    expect(screen.getByText("Heading")).toBeInTheDocument();
  });
});
