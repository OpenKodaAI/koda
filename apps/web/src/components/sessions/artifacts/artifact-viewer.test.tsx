import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ArtifactViewer } from "@/components/sessions/artifacts/artifact-viewer";
import type { ArtifactDetail } from "@/lib/contracts/artifacts";

function makeArtifact(overrides: Partial<ArtifactDetail> = {}): ArtifactDetail {
  return {
    id: "art_1",
    kind: "code",
    label: "agent.ts",
    mime_type: "text/plain",
    size_bytes: 128,
    created_at: "2026-05-02T00:00:00Z",
    download_url: "/api/runtime/artifacts/art_1/download?agent=ATLAS",
    preview_state: "available",
    ...overrides,
  };
}

function renderViewer(artifact: ArtifactDetail, fetchText: string) {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(fetchText, {
      status: 200,
      headers: { "Content-Type": "text/plain" },
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider initialLanguage="en-US">
        <ArtifactViewer artifact={artifact} showHeader={false} />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("ArtifactViewer dispatch", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders CodeViewer for kind='code'", async () => {
    renderViewer(
      makeArtifact({ kind: "code", label: "agent.ts" }),
      "const x = 42;\nconsole.log(x);",
    );
    await waitFor(() =>
      expect(screen.getByText(/typescript/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/const x = 42/)).toBeInTheDocument();
  });

  it("renders JsonViewer for kind='json' with parseable content", async () => {
    renderViewer(
      makeArtifact({ kind: "json", label: "config.json" }),
      JSON.stringify({ name: "Ryan", age: 30 }),
    );
    await waitFor(() =>
      expect(screen.getByText(/"name"/)).toBeInTheDocument(),
    );
  });

  it("renders fallback (with raw view) when JSON is invalid", async () => {
    renderViewer(makeArtifact({ kind: "json" }), "{not json");
    await waitFor(() =>
      expect(screen.getByText(/Invalid JSON/i)).toBeInTheDocument(),
    );
  });

  it("renders CsvViewer for kind='csv'", async () => {
    renderViewer(
      makeArtifact({ kind: "csv", label: "data.csv" }),
      "name,age\nryan,30\nlarissa,28",
    );
    await waitFor(() => {
      expect(screen.getByText("ryan")).toBeInTheDocument();
      expect(screen.getByText("larissa")).toBeInTheDocument();
    });
  });

  it("falls back to download for too-large artifacts", async () => {
    // 2 MB JSON > 1 MB cap
    const artifact = makeArtifact({ kind: "json", size_bytes: 2 * 1024 * 1024 });
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <I18nProvider initialLanguage="en-US">
          <ArtifactViewer artifact={artifact} showHeader={false} />
        </I18nProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/Too large to preview/i)).toBeInTheDocument();
    // Critical: never fetched the body for oversized artifacts.
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("falls back to download for unsupported kinds", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <I18nProvider initialLanguage="en-US">
          <ArtifactViewer
            artifact={makeArtifact({ kind: "image", mime_type: "image/png" })}
            showHeader={false}
          />
        </I18nProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("button", { name: /Download/i })).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("triggers fetch + click + revokeObjectURL on download", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("hello", { status: 200 }),
    );
    const create = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:abc");
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <I18nProvider initialLanguage="en-US">
          <ArtifactViewer
            artifact={makeArtifact({ kind: "image" })}
            showHeader={false}
          />
        </I18nProvider>
      </QueryClientProvider>,
    );

    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Download/i }));

    await waitFor(() => {
      expect(create).toHaveBeenCalled();
    });
    expect(click).toHaveBeenCalled();
    await waitFor(() => {
      expect(revoke).toHaveBeenCalledWith("blob:abc");
    });
  });
});
