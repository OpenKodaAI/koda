import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { MarkdownEditorField } from "@/components/control-plane/shared/markdown-editor-field";

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

    const modeTabs = screen.getByRole("tablist", { name: "Modo do editor Markdown" });
    const markdownButton = screen.getByRole("tab", { name: "Markdown" });
    const previewButton = screen.getByRole("tab", { name: "Prévia" });
    expect(modeTabs).toContainElement(previewButton);
    expect(modeTabs).toContainElement(markdownButton);
    expect(markdownButton).toHaveAttribute("aria-selected", "true");
    expect(previewButton).toHaveAttribute("aria-selected", "false");
    expect(screen.queryByRole("button", { name: "Editar" })).not.toBeInTheDocument();

    const textbox = screen.getByRole("textbox");
    expect(textbox).toBeInTheDocument();

    await user.type(textbox, " atualizado");
    expect(onChange).toHaveBeenCalled();

    await user.click(previewButton);
    expect(previewButton).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Heading")).toBeInTheDocument();
  });
});
