import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AsyncActionButton, BackgroundRefreshIndicator } from "@/components/ui/async-feedback";

describe("async feedback primitives", () => {
  it("marks action buttons as busy when loading", () => {
    render(
      <AsyncActionButton loading loadingLabel="Salvando">
        Salvar
      </AsyncActionButton>,
    );

    expect(screen.getByRole("button")).toHaveAttribute("aria-busy", "true");
  });

  it("shows a subtle refresh state for background updates", () => {
    render(<BackgroundRefreshIndicator refreshing label="Atualizando" />);

    expect(screen.getByRole("status")).toHaveTextContent("Atualizando");
  });
});
