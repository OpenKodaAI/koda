import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { RailSearch } from "@/components/sessions/rail/rail-search";
import { PageSearchField } from "@/components/ui/page-primitives";

describe("search fields", () => {
  it("renders PageSearchField with spinner-only loading and clear action", () => {
    const onChange = vi.fn();

    render(
      <PageSearchField
        value="beta"
        onChange={onChange}
        placeholder="Search"
        loading
        loadingLabel="Searching"
        clearLabel="Clear search"
      />,
    );

    expect(screen.getByRole("status", { name: "Searching" })).toBeInTheDocument();
    expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Clear search" }));

    expect(onChange).toHaveBeenCalledWith("");
  });

  it("renders RailSearch with a spinner and no visible loading copy", () => {
    const onChange = vi.fn();

    render(
      <I18nProvider initialLanguage="en-US">
        <RailSearch value="alpha" onChange={onChange} loading />
      </I18nProvider>,
    );

    expect(
      screen.getByRole("status", { name: "Searching conversations" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Clear search" }));

    expect(onChange).toHaveBeenCalledWith("");
  });
});
