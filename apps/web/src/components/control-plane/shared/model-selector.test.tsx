/* eslint-disable @next/next/no-img-element */

import type { ImgHTMLAttributes } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ModelSelector } from "./model-selector";
import { translateForLanguage } from "@/lib/i18n";

vi.mock("next/image", () => ({
  default: (props: ImgHTMLAttributes<HTMLImageElement>) => (
    <img {...props} alt={props.alt || ""} />
  ),
}));

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

  // F-ADM-06 (M6-E3-T5): the video and music generation functions only
  // raise, so their default slots read "Not available yet" and cannot be set.
  describe("video and music slots", () => {
    const catalog = {
      image: [{ provider_id: "codex", model_id: "gpt-image-1", title: "GPT Image" }],
      video: [{ provider_id: "codex", model_id: "sora-2", title: "Sora 2" }],
      music: [{ provider_id: "elevenlabs", model_id: "music_v1", title: "Music v1" }],
    };

    for (const functionId of ["video", "music"]) {
      it(`shows the ${functionId} slot as not available yet and never opens it`, () => {
        const onChange = vi.fn();
        render(
          <ModelSelector
            label={functionId}
            value=""
            onChange={onChange}
            providers={{}}
            enabledProviders={["codex", "elevenlabs"]}
            functionalCatalog={catalog}
            functionId={functionId}
            emptyLabel="Selecione um modelo padrão"
          />,
        );

        const badge = translateForLanguage("pt-BR", "controlPlane.modelFunctions.unavailable.badge");
        const description = translateForLanguage(
          "pt-BR",
          "controlPlane.modelFunctions.unavailable.description",
        );
        const trigger = screen.getByRole("button", { name: new RegExp(`^${functionId}`) });
        expect(trigger).toBeDisabled();
        expect(trigger).toHaveTextContent(badge);
        expect(screen.getByText(description)).toBeInTheDocument();

        fireEvent.click(trigger);
        expect(screen.queryByPlaceholderText("Buscar modelo...")).not.toBeInTheDocument();
        expect(onChange).not.toHaveBeenCalled();
      });
    }

    it("keeps a stored video default visible but locked", () => {
      render(
        <ModelSelector
          label="video"
          value="codex:sora-2"
          onChange={vi.fn()}
          providers={{}}
          enabledProviders={["codex"]}
          functionalCatalog={catalog}
          functionId="video"
        />,
      );

      const trigger = screen.getByRole("button", { name: /^video/ });
      expect(trigger).toBeDisabled();
      expect(trigger).toHaveTextContent("Sora 2");
    });

    it("keeps the image slot selectable", () => {
      render(
        <ModelSelector
          label="image"
          value=""
          onChange={vi.fn()}
          providers={{}}
          enabledProviders={["codex"]}
          functionalCatalog={catalog}
          functionId="image"
        />,
      );

      const trigger = screen.getByRole("button", { name: "image" });
      expect(trigger).toBeEnabled();
      fireEvent.click(trigger);
      expect(screen.getByPlaceholderText("Buscar modelo...")).toBeInTheDocument();
    });

    it("words the label in both locales", () => {
      expect(translateForLanguage("en-US", "controlPlane.modelFunctions.unavailable.badge")).toBe(
        "Not available yet",
      );
      expect(translateForLanguage("pt-BR", "controlPlane.modelFunctions.unavailable.badge")).toBe(
        "Ainda não disponível",
      );
    });
  });
});
