import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GlobalDefaultsPanel } from "@/components/control-plane/catalog/global-defaults-panel";

const refreshMock = vi.fn();
const showToastMock = vi.fn();
const originalFetch = globalThis.fetch;

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    refresh: refreshMock,
  }),
}));

vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({
    showToast: showToastMock,
  }),
}));

vi.mock("@/hooks/use-app-i18n", () => ({
  useAppI18n: () => ({
    tl: (value: string) => value,
  }),
}));

describe("GlobalDefaultsPanel", () => {
  beforeEach(() => {
    refreshMock.mockReset();
    showToastMock.mockReset();
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ sections: { behavior: { enabled: true } }, version: 2 }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    ) as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("saves global defaults through the canonical route and method", async () => {
    const user = userEvent.setup();

    render(
      <GlobalDefaultsPanel
        sections={{ behavior: { enabled: true } }}
        version={1}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Defaults globais/i }));
    await user.click(screen.getByRole("button", { name: "Salvar defaults" }));

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/control-plane/global-defaults",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ sections: { behavior: { enabled: true } } }),
        }),
      );
    });
  });
});
