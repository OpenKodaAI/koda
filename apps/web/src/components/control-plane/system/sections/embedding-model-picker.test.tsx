import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "@/hooks/use-toast";
import { EmbeddingModelPicker } from "./embedding-model-picker";

vi.mock("@/hooks/use-app-i18n", () => ({
  useAppI18n: () => ({ tl: (s: string) => s }),
}));

const baseModel = {
  id: "paraphrase-multilingual-minilm",
  repo_id: "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
  title: "Paraphrase Multilingual MiniLM",
  description: "Recommended starting point.",
  size_mb: 470,
  dimension: 384,
  languages: ["pt", "en"],
  quality: 3,
  speed: 4,
  hardware_hint: "cpu/mps",
  multilingual: true,
  is_default_install: false,
  installed: true,
  disk_bytes: 470_000_000,
  active_job: null,
};

const altModel = {
  ...baseModel,
  id: "multilingual-e5-small",
  repo_id: "intfloat/multilingual-e5-small",
  title: "Multilingual E5 Small",
  description: "Higher quality, slower.",
  is_default_install: false,
  installed: false,
  disk_bytes: 0,
};

const defaultPayload = {
  items: [baseModel, altModel],
  active: baseModel.id,
  default: baseModel.id,
};

function withToast(node: React.ReactNode) {
  // Each render gets a fresh QueryClient so cache state never leaks between
  // tests (relevant now that the picker uses TanStack Query for the catalog).
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return (
    <QueryClientProvider client={client}>
      <ToastProvider>{node}</ToastProvider>
    </QueryClientProvider>
  );
}

describe("EmbeddingModelPicker", () => {
  beforeEach(() => {
    vi.spyOn(window, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/embedding/models") && !url.endsWith("/select") && !url.endsWith("/download")) {
        return new Response(JSON.stringify(defaultPayload), { status: 200 });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the catalog with active badge on the current model", async () => {
    render(withToast(<EmbeddingModelPicker />));
    await waitFor(() => expect(screen.getByText("Paraphrase Multilingual MiniLM")).toBeInTheDocument());
    expect(screen.getByText("Multilingual E5 Small")).toBeInTheDocument();
    // The active model gets the "Ativo" chip.
    expect(screen.getByText("Ativo")).toBeInTheDocument();
    // No "Padrão" tag — Koda no longer ships a pre-installed model.
    expect(screen.queryByText("Padrão")).toBeNull();
  });

  it("shows the missing-model alert when memory is enabled and no model is installed", async () => {
    const noneInstalledPayload = {
      items: [
        { ...baseModel, installed: false, disk_bytes: 0 },
        altModel,
      ],
      active: baseModel.id,
      default: baseModel.id,
    };
    vi.spyOn(window, "fetch").mockImplementation(async () => {
      return new Response(JSON.stringify(noneInstalledPayload), { status: 200 });
    });
    render(withToast(<EmbeddingModelPicker memoryEnabled />));
    await waitFor(() => screen.getByText("Paraphrase Multilingual MiniLM"));
    expect(screen.getByTestId("embedding-missing-model-alert")).toBeInTheDocument();
  });

  it("hides the missing-model alert when memory is disabled", async () => {
    const noneInstalledPayload = {
      items: [
        { ...baseModel, installed: false, disk_bytes: 0 },
        altModel,
      ],
      active: baseModel.id,
      default: baseModel.id,
    };
    vi.spyOn(window, "fetch").mockImplementation(async () => {
      return new Response(JSON.stringify(noneInstalledPayload), { status: 200 });
    });
    render(withToast(<EmbeddingModelPicker memoryEnabled={false} />));
    await waitFor(() => screen.getByText("Paraphrase Multilingual MiniLM"));
    expect(screen.queryByTestId("embedding-missing-model-alert")).toBeNull();
  });

  it("hides the missing-model alert when at least one model is installed", async () => {
    render(withToast(<EmbeddingModelPicker memoryEnabled />));
    await waitFor(() => screen.getByText("Paraphrase Multilingual MiniLM"));
    expect(screen.queryByTestId("embedding-missing-model-alert")).toBeNull();
  });

  it("shows download button only for missing models", async () => {
    render(withToast(<EmbeddingModelPicker />));
    await waitFor(() => screen.getByText("Multilingual E5 Small"));
    expect(screen.getByTestId("embedding-download-multilingual-e5-small")).toBeInTheDocument();
    expect(screen.queryByTestId("embedding-download-paraphrase-multilingual-minilm")).toBeNull();
  });

  it("shows 'Em uso' on the active installed model and 'Usar este' on others", async () => {
    render(withToast(<EmbeddingModelPicker />));
    await waitFor(() => screen.getByText("Paraphrase Multilingual MiniLM"));
    const activeBtn = screen.getByTestId("embedding-select-paraphrase-multilingual-minilm");
    expect(activeBtn).toBeDisabled();
    expect(activeBtn).toHaveTextContent(/Em uso/i);
  });

  it("calls the select endpoint when clicking 'Usar este' on an installed alternative", async () => {
    const user = userEvent.setup();
    const installedAlt = { ...altModel, installed: true, disk_bytes: 470_000_000 };
    const swappedPayload = {
      items: [baseModel, installedAlt],
      active: baseModel.id,
      default: baseModel.id,
    };
    const fetchMock = vi.spyOn(window, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "GET" && url.endsWith("/embedding/models")) {
        return new Response(JSON.stringify(swappedPayload), { status: 200 });
      }
      if (method === "POST" && url.endsWith(`/embedding/models/${installedAlt.id}/select`)) {
        return new Response(
          JSON.stringify({ ...swappedPayload, active: installedAlt.id }),
          { status: 200 },
        );
      }
      throw new Error(`unexpected fetch ${method} ${url}`);
    });
    render(withToast(<EmbeddingModelPicker />));
    await waitFor(() => screen.getByText("Multilingual E5 Small"));
    const switchBtn = screen.getByTestId(`embedding-select-${installedAlt.id}`);
    await user.click(switchBtn);
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(`/embedding/models/${installedAlt.id}/select`),
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("shows the delete button on every installed model — including the active one", async () => {
    const installedAlt = { ...altModel, installed: true, disk_bytes: 470_000_000 };
    const swappedPayload = {
      items: [baseModel, installedAlt],
      active: baseModel.id,
      default: baseModel.id,
    };
    vi.spyOn(window, "fetch").mockImplementation(async () => {
      return new Response(JSON.stringify(swappedPayload), { status: 200 });
    });
    render(withToast(<EmbeddingModelPicker />));
    await waitFor(() => screen.getByText("Multilingual E5 Small"));
    // Active installed model: delete button IS rendered (operator can wipe
    // the active one; backend auto-switches to another installed model).
    expect(screen.getByTestId(`embedding-delete-${baseModel.id}`)).toBeInTheDocument();
    // Non-active installed model: also rendered.
    expect(screen.getByTestId(`embedding-delete-${installedAlt.id}`)).toBeInTheDocument();
  });

  it("does not render a delete button on uninstalled models", async () => {
    // altModel has installed: false in the default fixture — nothing to wipe.
    render(withToast(<EmbeddingModelPicker />));
    await waitFor(() => screen.getByText("Multilingual E5 Small"));
    expect(screen.queryByTestId(`embedding-delete-${altModel.id}`)).toBeNull();
  });

  it("requires a confirmation click before calling DELETE on a model", async () => {
    const user = userEvent.setup();
    const installedAlt = { ...altModel, installed: true, disk_bytes: 470_000_000 };
    const swappedPayload = {
      items: [baseModel, installedAlt],
      active: baseModel.id,
      default: baseModel.id,
    };
    const afterDeletePayload = {
      ...swappedPayload,
      items: [baseModel, { ...installedAlt, installed: false, disk_bytes: 0 }],
    };
    const fetchMock = vi.spyOn(window, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "GET" && url.endsWith("/embedding/models")) {
        return new Response(JSON.stringify(swappedPayload), { status: 200 });
      }
      if (method === "DELETE" && url.endsWith(`/embedding/models/${installedAlt.id}`)) {
        return new Response(JSON.stringify(afterDeletePayload), { status: 200 });
      }
      throw new Error(`unexpected fetch ${method} ${url}`);
    });
    render(withToast(<EmbeddingModelPicker />));
    await waitFor(() => screen.getByText("Multilingual E5 Small"));
    const deleteBtn = screen.getByTestId(`embedding-delete-${installedAlt.id}`);
    // First click: no DELETE yet; the button enters confirm mode.
    await user.click(deleteBtn);
    expect(
      fetchMock.mock.calls.some(
        ([, init]) => (init as RequestInit | undefined)?.method === "DELETE",
      ),
    ).toBe(false);
    // Second click confirms the deletion.
    await user.click(screen.getByTestId(`embedding-delete-${installedAlt.id}`));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(`/embedding/models/${installedAlt.id}`),
        expect.objectContaining({ method: "DELETE" }),
      ),
    );
  });
});
