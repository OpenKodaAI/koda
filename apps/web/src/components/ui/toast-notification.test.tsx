import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ToastNotification } from "@/components/ui/toast-notification";
import { ToastProvider, useToast } from "@/hooks/use-toast";

function ToastProbe() {
  const { showToast } = useToast();
  return (
    <button
      type="button"
      onClick={() =>
        showToast("Retomando download…", "warning", {
          title: "Baixando modelo Kokoro",
          durationMs: 10_000,
          action: {
            label: "Cancelar",
            ariaLabel: "Cancelar download",
            onClick: vi.fn(),
          },
        })
      }
    >
      Show toast
    </button>
  );
}

describe("ToastNotification translations", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.cookie = "atlas.locale=; path=/; max-age=0";
  });

  it("translates literal title, message, action, and close label at render time", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider initialLanguage="es-ES">
        <ToastProvider>
          <ToastProbe />
          <ToastNotification />
        </ToastProvider>
      </I18nProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Show toast" }));

    expect(screen.getByText("Descargando modelo Kokoro")).toBeInTheDocument();
    expect(screen.getByText("Reanudando descarga...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancelar descarga" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Descartar notificación" })).toBeInTheDocument();
  });
});
