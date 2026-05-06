/* eslint-disable @next/next/no-img-element */

import type { ImgHTMLAttributes } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ModelSelector } from "./model-selector";

vi.mock("next/image", () => ({
  default: (props: ImgHTMLAttributes<HTMLImageElement>) => (
    <img {...props} alt={props.alt || ""} />
  ),
}));

vi.mock("@/hooks/use-app-i18n", () => ({
  useAppI18n: () => ({
    tl: (value: string) => value,
  }),
}));

describe("ModelSelector", () => {
  it("renders a search input inside the dropdown and filters models", () => {
    const onChange = vi.fn();

    render(
      <ModelSelector
        label="Modelo"
        value=""
        onChange={onChange}
        providers={{
          codex: {
            title: "OpenAI",
            category: "general",
            available_models: ["gpt-5.2"],
          },
          claude: {
            title: "Anthropic",
            category: "general",
            available_models: ["claude-sonnet-4-5"],
          },
        }}
        enabledProviders={["codex", "claude"]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Modelo" }));

    const search = screen.getByPlaceholderText("Buscar modelo...");
    expect(search).toBeInTheDocument();
    expect(screen.getByText("gpt-5.2")).toBeInTheDocument();

    fireEvent.change(search, { target: { value: "sonnet" } });

    expect(screen.queryByText("gpt-5.2")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("claude-sonnet-4-5").closest("button")!);

    expect(onChange).toHaveBeenCalledWith("claude:claude-sonnet-4-5");
  });

  it("keeps unavailable settings options visible but not selectable", () => {
    const onChange = vi.fn();

    render(
      <ModelSelector
        label="Modelo"
        value=""
        onChange={onChange}
        providers={{}}
        enabledProviders={["codex"]}
        functionalCatalog={{
          general: [
            {
              provider_id: "codex",
              provider_title: "OpenAI",
              model_id: "gpt-5.2",
              title: "GPT-5.2",
            },
          ],
        }}
        functionId="general"
        isOptionDisabled={() => true}
        disabledOptionLabel="indisponível no momento"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Modelo" }));

    expect(screen.getByText("indisponível no momento")).toBeInTheDocument();
    fireEvent.click(screen.getByText("gpt-5.2").closest("button")!);

    expect(onChange).not.toHaveBeenCalled();
  });
});
