import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ToastProvider } from "@/hooks/use-toast";
import { RuntimeFilesPanel } from "@/components/runtime/runtime-files-panel";
import type {
  RuntimeWorkspaceStatus,
  RuntimeWorkspaceTreeEntry,
} from "@/lib/runtime-types";

const workspaceTree: RuntimeWorkspaceTreeEntry[] = [
  { name: "README.md", path: "README.md", is_dir: false, size: 24 },
  { name: "src", path: "src", is_dir: true },
];

function renderPanel({
  mutate = vi.fn().mockResolvedValue({ ok: true }),
  fetchResource = vi.fn(),
  workspaceStatus = {
    ok: true,
    text: "## main\n M README.md\n?? src/new.ts",
  },
}: {
  mutate?: ReturnType<typeof vi.fn>;
  fetchResource?: ReturnType<typeof vi.fn>;
  workspaceStatus?: RuntimeWorkspaceStatus;
} = {}) {
  fetchResource.mockImplementation((resourcePath: string, searchParams?: URLSearchParams) => {
    if (resourcePath === "workspace/tree") {
      const path = searchParams?.get("path") || "";
      return Promise.resolve({
        items:
          path === "src"
            ? [
                {
                  name: "app.tsx",
                  path: "src/app.tsx",
                  is_dir: false,
                  size: 36,
                },
              ]
            : workspaceTree,
      });
    }

    if (resourcePath === "workspace/file") {
      const path = searchParams?.get("path") || "README.md";
      return Promise.resolve({
        path,
        content: path.endsWith(".md") ? "# Runtime\n\nhello" : "export const runtime = true;",
        truncated: false,
      });
    }

    if (resourcePath === "workspace/status") {
      return Promise.resolve(workspaceStatus);
    }

    if (resourcePath === "workspace/search") {
      const query = searchParams?.get("q") || "";
      return Promise.resolve({
        ok: true,
        query,
        items: query
          ? [
              {
                path: "src/app.tsx",
                line_number: 1,
                column: 14,
                line: "export const runtime = true;",
                preview: "export const runtime = true;",
                match: "runtime",
                start: 13,
                end: 20,
              },
            ]
          : [],
        truncated: false,
        searched_files: 2,
      });
    }

    if (resourcePath === "workspace/diff") {
      return Promise.resolve({
        ok: true,
        text: [
          "diff --git a/README.md b/README.md",
          "--- a/README.md",
          "+++ b/README.md",
          "@@ -1,3 +1,3 @@",
          " # Runtime",
          "",
          "-hello",
          "+updated",
        ].join("\n"),
        truncated: false,
      });
    }

    return Promise.resolve({});
  });

  render(
    <I18nProvider initialLanguage="pt-BR">
      <ToastProvider>
        <RuntimeFilesPanel
          taskId={42}
          workspaceTree={workspaceTree}
          workspaceStatus={workspaceStatus}
          mutate={mutate}
          fetchResource={fetchResource}
        />
      </ToastProvider>
    </I18nProvider>,
  );

  return { mutate, fetchResource };
}

describe("RuntimeFilesPanel", () => {
  it("opens, previews, edits and saves a workspace file", async () => {
    const { mutate, fetchResource } = renderPanel();

    fireEvent.click(screen.getAllByRole("button", { name: /README\.md/i })[0]);

    await waitFor(() =>
      expect(fetchResource).toHaveBeenCalledWith(
        "workspace/file",
        expect.any(URLSearchParams),
      ),
    );
    await waitFor(() => expect(screen.getAllByText("README.md").length).toBeGreaterThan(1));

    fireEvent.click(screen.getByRole("button", { name: /preview|prévia/i }));
    expect(await screen.findByRole("heading", { name: "Runtime" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /código|code/i }));
    fireEvent.click(screen.getByRole("button", { name: /^editar$/i }));

    const editor = screen.getByRole("textbox");
    fireEvent.change(editor, { target: { value: "# Runtime\n\nupdated" } });
    fireEvent.click(screen.getByRole("button", { name: /salvar|save/i }));

    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith("workspace/write", {
        body: { path: "README.md", content: "# Runtime\n\nupdated" },
      }),
    );
  });

  it("cancels editing without leaving the active editor dirty", async () => {
    const { mutate } = renderPanel();

    fireEvent.click(screen.getAllByRole("button", { name: /README\.md/i })[0]);
    await screen.findByText("# Runtime");
    fireEvent.click(screen.getByRole("button", { name: /^editar$/i }));

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "# Runtime\n\nlocal draft" },
    });
    expect(screen.getByText("Não salvo")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /cancelar/i }));

    expect(screen.queryByText("Não salvo")).not.toBeInTheDocument();
    expect(screen.getByText("Salvo")).toBeInTheDocument();
    expect(mutate).not.toHaveBeenCalledWith("workspace/write", expect.anything());
  });

  it("expands directories and creates files and folders inline", async () => {
    const { mutate, fetchResource } = renderPanel();

    fireEvent.click(screen.getByRole("button", { name: /^src/i }));
    await waitFor(() =>
      expect(fetchResource).toHaveBeenCalledWith(
        "workspace/tree",
        expect.any(URLSearchParams),
      ),
    );
    expect(await screen.findByRole("button", { name: /app\.tsx/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /novo arquivo/i }));
    fireEvent.change(screen.getByLabelText("Nome"), {
      target: { value: "notes.md" },
    });
    fireEvent.submit(screen.getByLabelText("Nome").closest("form") as HTMLFormElement);

    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith("workspace/create", {
        body: { path: "notes.md", kind: "file", content: "" },
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: /nova pasta/i }));
    fireEvent.change(screen.getByLabelText("Nome"), {
      target: { value: "docs" },
    });
    fireEvent.submit(screen.getByLabelText("Nome").closest("form") as HTMLFormElement);

    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith("workspace/create", {
        body: { path: "docs", kind: "directory", content: "" },
      }),
    );
  });

  it("renames and deletes files through inline IDE actions", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const { mutate } = renderPanel();

    fireEvent.click(screen.getAllByRole("button", { name: /ações do arquivo/i })[0]);
    fireEvent.click(await screen.findByRole("menuitem", { name: /renomear/i }));
    fireEvent.change(screen.getByLabelText("Nome"), {
      target: { value: "README-updated.md" },
    });
    fireEvent.submit(screen.getByLabelText("Nome").closest("form") as HTMLFormElement);

    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith("workspace/rename", {
        body: { from_path: "README.md", to_path: "README-updated.md" },
      }),
    );

    fireEvent.click(screen.getAllByRole("button", { name: /README\.md/i })[0]);
    await screen.findByText("# Runtime");
    fireEvent.click(screen.getByRole("button", { name: /deletar arquivo/i }));
    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith("workspace/delete", {
        body: { path: "README.md" },
      }),
    );

    confirmSpy.mockRestore();
  });

  it("renames folders while preserving open child editors", async () => {
    const { mutate } = renderPanel();

    fireEvent.click(screen.getByRole("button", { name: /^src/i }));
    fireEvent.click(await screen.findByRole("button", { name: /app\.tsx/i }));
    await screen.findByText("src/app.tsx");

    fireEvent.click(screen.getByRole("button", { name: /ações da pasta/i }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /renomear/i }));
    fireEvent.change(screen.getByLabelText("Nome"), {
      target: { value: "lib" },
    });
    fireEvent.submit(screen.getByLabelText("Nome").closest("form") as HTMLFormElement);

    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith("workspace/rename", {
        body: { from_path: "src", to_path: "lib" },
      }),
    );
    expect(screen.getByText("lib/app.tsx")).toBeInTheDocument();
  });

  it("shows git changes and opens a read-only diff view", async () => {
    const { fetchResource } = renderPanel();

    expect(screen.getByText("Alterações")).toBeInTheDocument();
    expect(screen.getAllByText("README.md").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /ver diff de README\.md/i }));

    await waitFor(() =>
      expect(fetchResource).toHaveBeenCalledWith(
        "workspace/diff",
        expect.any(URLSearchParams),
      ),
    );
    expect(await screen.findByText("Antes")).toBeInTheDocument();
    expect(screen.getByText("Depois")).toBeInTheDocument();
    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.getByText("updated")).toBeInTheDocument();
  });

  it("supports IDE-style search matching options", async () => {
    renderPanel();

    fireEvent.click(screen.getAllByRole("button", { name: /README\.md/i })[0]);
    await screen.findByText("# Runtime");

    fireEvent.click(screen.getByRole("button", { name: /^buscar$/i }));
    fireEvent.change(screen.getByPlaceholderText("Buscar..."), {
      target: { value: "runtime" },
    });

    expect(await screen.findByText("1/1")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /palavra inteira/i }).length).toBeGreaterThan(1);
    expect(screen.getAllByRole("button", { name: /expressão regular/i }).length).toBeGreaterThan(1);

    fireEvent.click(screen.getAllByRole("button", { name: /maiúsculas\/minúsculas/i }).at(-1)!);
    await waitFor(() => expect(screen.getByText("0/0")).toBeInTheDocument());
  });

  it("searches files across the workspace and opens a result", async () => {
    const { fetchResource } = renderPanel();

    fireEvent.change(screen.getByRole("searchbox", { name: /buscar no espaço de trabalho/i }), {
      target: { value: "runtime" },
    });

    expect(await screen.findByText("Correspondências no espaço de trabalho")).toBeInTheDocument();
    expect(await screen.findByText("src/app.tsx")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /src\/app\.tsx/i }));

    await waitFor(() =>
      expect(fetchResource).toHaveBeenCalledWith(
        "workspace/file",
        expect.any(URLSearchParams),
      ),
    );
  });
});
