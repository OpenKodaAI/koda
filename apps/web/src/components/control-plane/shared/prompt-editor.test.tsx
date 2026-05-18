import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PromptEditor } from "@/components/control-plane/shared/prompt-editor";

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

describe("PromptEditor", () => {
  it("uses inline Preview and Markdown tabs without a separate toggle button", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(
      <PromptEditor
        value="# System prompt"
        onChange={onChange}
        placeholder="Write instructions"
      />,
    );

    const tablist = screen.getByRole("tablist", { name: "Markdown editor mode" });
    const previewTab = screen.getByRole("tab", { name: "Preview" });
    const markdownTab = screen.getByRole("tab", { name: "Markdown" });
    expect(tablist).toContainElement(previewTab);
    expect(tablist).toContainElement(markdownTab);
    expect(markdownTab).toHaveAttribute("aria-selected", "true");
    expect(previewTab).toHaveAttribute("aria-selected", "false");
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();

    const textbox = screen.getByRole("textbox");
    await user.type(textbox, " updated");
    expect(onChange).toHaveBeenCalled();

    await user.click(previewTab);
    expect(previewTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("System prompt")).toBeInTheDocument();
  });
});
