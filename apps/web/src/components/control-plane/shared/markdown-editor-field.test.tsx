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

  it("defaults to writing mode and still supports preview, copy and paste actions", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(
      <MarkdownEditorField
        label="Instructions"
        value="# Heading"
        onChange={onChange}
      />,
    );

    expect(screen.getByText("Lado a lado")).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copiar" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Colar" })).toBeInTheDocument();
    expect(screen.getByText("Escrever").closest("button")?.className).not.toContain("button-pill");

    await user.type(screen.getByRole("textbox"), " atualizado");
    expect(onChange).toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Preview" }));
    expect(screen.getByText("Heading")).toBeInTheDocument();
  });
});
