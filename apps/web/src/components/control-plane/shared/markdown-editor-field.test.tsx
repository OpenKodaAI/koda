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

    const modeTabs = screen.getByRole("tablist", { name: "Modo do editor Markdown" });
    const markdownButton = screen.getByRole("tab", { name: "Markdown" });
    const previewButton = screen.getByRole("tab", { name: "Preview" });
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
