import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FieldShell } from "./field-shell";

vi.mock("@/hooks/use-app-i18n", () => ({
  useAppI18n: () => ({ tl: (value: string) => value }),
}));

describe("FieldShell", () => {
  it("does not render an error region when no error is provided", () => {
    render(
      <FieldShell label="Budget">
        <input data-testid="child" />
      </FieldShell>,
    );
    expect(screen.queryByRole("alert")).toBeNull();
    const label = screen.getByText("Budget").closest("label");
    expect(label?.getAttribute("aria-invalid")).toBeNull();
  });

  it("renders inline error, role=alert and aria-invalid when error is set", () => {
    render(
      <FieldShell
        label="Budget"
        error="Orçamento total deve ser maior ou igual ao orçamento por tarefa."
      >
        <input data-testid="child" />
      </FieldShell>,
    );
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Orçamento total deve ser maior");
    const label = screen.getByText("Budget").closest("label");
    expect(label?.getAttribute("aria-invalid")).toBe("true");
    const describedBy = label?.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    expect(alert.id).toBe(describedBy);
  });

  it("treats null error as no error", () => {
    render(
      <FieldShell label="Budget" error={null}>
        <input />
      </FieldShell>,
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
