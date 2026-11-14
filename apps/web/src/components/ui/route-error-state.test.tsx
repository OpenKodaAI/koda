import fs from "node:fs";
import path from "node:path";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ComponentType } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AppError from "@/app/error";
import ControlPlaneError from "@/app/control-plane/error";
import MemoryError from "@/app/memory/error";
import RuntimeError from "@/app/runtime/error";
import SessionsError from "@/app/sessions/error";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ErrorState } from "@/components/ui/async-feedback";
import { LOCALE_COOKIE_KEY, translateForLanguage, type AppLanguage } from "@/lib/i18n";

type Boundary = ComponentType<{ error: Error & { digest?: string }; reset: () => void }>;

// [source file, boundary, title key, fallback description key]
const BOUNDARIES: Array<[string, Boundary, string, string]> = [
  [
    "app/error.tsx",
    AppError,
    "generated.routes.we_hit_a_route_error_e67cad31",
    "generated.routes.the_page_could_not_be_rendered_4d58a8d1",
  ],
  [
    "app/control-plane/error.tsx",
    ControlPlaneError,
    "generated.routes.control_plane_unavailable_ebef0c95",
    "generated.routes.the_control_plane_section_could_not_be_loade_8b86eed7",
  ],
  [
    "app/memory/error.tsx",
    MemoryError,
    "generated.routes.memory_workspace_unavailable_55cf16d1",
    "generated.routes.the_memory_section_could_not_be_loaded_5ee3b956",
  ],
  [
    "app/runtime/error.tsx",
    RuntimeError,
    "generated.routes.runtime_unavailable_27ef08e4",
    "generated.routes.the_runtime_section_could_not_be_loaded_0bc0b972",
  ],
  [
    "app/sessions/error.tsx",
    SessionsError,
    "generated.routes.sessions_unavailable_2def7e52",
    "generated.routes.the_sessions_workspace_could_not_be_loaded_d61f1050",
  ],
];

function renderBoundary(Boundary: Boundary, error: Error, language: AppLanguage = "en-US") {
  const reset = vi.fn();
  render(
    <I18nProvider initialLanguage={language}>
      <Boundary error={error} reset={reset} />
    </I18nProvider>,
  );
  return reset;
}

beforeEach(() => {
  // The provider persists the language, so clear it to honour initialLanguage.
  window.localStorage.clear();
  document.cookie = `${LOCALE_COOKIE_KEY}=; path=/; max-age=0`;
});

describe("route error boundaries", () => {
  it.each(BOUNDARIES)(
    "%s shows its own title, the error message and a retry that resets the segment",
    (_file, Boundary, titleKey) => {
      const reset = renderBoundary(Boundary, new Error("upstream timed out"));

      expect(screen.getByText(translateForLanguage("en-US", titleKey))).toBeInTheDocument();
      expect(screen.getByText("upstream timed out")).toBeInTheDocument();
      fireEvent.click(
        screen.getByRole("button", { name: translateForLanguage("en-US", "async.retry") }),
      );
      expect(reset).toHaveBeenCalledTimes(1);
    },
  );

  it.each(BOUNDARIES)(
    "%s falls back to its own description when the error has no message",
    (_file, Boundary, _titleKey, descriptionKey) => {
      renderBoundary(Boundary, new Error(""));

      expect(screen.getByText(translateForLanguage("en-US", descriptionKey))).toBeInTheDocument();
    },
  );

  it.each(BOUNDARIES)(
    "%s renders the same error state, retry copy included, as ErrorState",
    (_file, Boundary, titleKey) => {
      renderBoundary(Boundary, new Error("boom"), "pt-BR");
      const boundaryButton = screen.getByRole("button");
      const boundaryState = boundaryButton.closest(".empty-state");

      render(
        <I18nProvider initialLanguage="pt-BR">
          <div data-testid="reference">
            <ErrorState
              title={translateForLanguage("pt-BR", titleKey)}
              description="boom"
              onRetry={() => undefined}
            />
          </div>
        </I18nProvider>,
      );
      const referenceState = screen.getByTestId("reference").firstElementChild;

      expect(boundaryButton).toHaveAccessibleName(translateForLanguage("pt-BR", "async.retry"));
      expect(boundaryState).not.toBeNull();
      expect(boundaryState?.outerHTML).toBe(referenceState?.outerHTML);
    },
  );

  it.each(BOUNDARIES)("%s is a single call to the shared boundary factory", (file) => {
    const source = fs.readFileSync(path.join(process.cwd(), "src", file), "utf8");

    expect(source).toMatch(/export default createRouteErrorBoundary\(/);
    expect(source).not.toMatch(/RouteErrorState|<[A-Za-z]/);
  });
});
