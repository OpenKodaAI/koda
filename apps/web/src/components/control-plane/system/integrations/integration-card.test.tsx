import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { IntegrationCard } from "@/components/control-plane/system/integrations/integration-card";
import type { UnifiedIntegrationEntry } from "@/components/control-plane/system/integrations/integration-marketplace-data";

vi.mock("@/hooks/use-app-i18n", () => ({
  useAppI18n: () => ({
    tl: (value: string) => value,
  }),
}));

vi.mock("@/components/control-plane/system/integrations/integration-logos", () => ({
  renderIntegrationLogo: () => null,
}));

function makeEntry(
  overrides: Partial<UnifiedIntegrationEntry> = {},
): UnifiedIntegrationEntry {
  return {
    id: "core:browser",
    key: "browser",
    kind: "core",
    status: "connected",
    label: "Browser",
    tagline: "Navegação",
    description: "Navegação governada",
    category: "development",
    logoKey: "browser",
    gradientFrom: "#7C9CFF",
    gradientTo: "#3656D4",
    promptExample: "",
    capabilities: [],
    metadata: {
      type: "native",
    },
    searchText: "browser navegacao",
    core: {
      entry: {} as never,
    },
    ...overrides,
  };
}

describe("IntegrationCard", () => {
  it("keeps connected cards minimal and uses the success token on the check", () => {
    render(<IntegrationCard entry={makeEntry()} onClick={() => {}} />);

    const card = screen.getByRole("button", { name: /Browser — Conectado/i });
    expect(card).toHaveClass("integration-card--connected");
    expect(card.getAttribute("style") ?? "").not.toContain("border-left");

    const checkIcon = card.querySelector(".lucide-check");
    expect(checkIcon).not.toBeNull();
    // The check icon inherits success color from its container's CSS class
    const container = checkIcon!.closest("div");
    expect(container?.className).toContain("text-[var(--tone-success-text)]");
  });
});
