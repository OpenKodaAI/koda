"use client";

import { useAppI18n } from "@/hooks/use-app-i18n";
import { renderIntegrationLogo } from "./integration-logos";
import type { UnifiedIntegrationEntry } from "./integration-marketplace-data";
import {
  IntegrationCardStatusIndicator,
  integrationCardRootClassName,
} from "./integration-card-presentation";

/* ------------------------------------------------------------------ */
/*  Integration card for the marketplace grid                          */
/* ------------------------------------------------------------------ */

export function IntegrationCard({
  entry,
  onClick,
}: {
  entry: UnifiedIntegrationEntry;
  onClick: () => void;
}) {
  const { tl } = useAppI18n();

  const status = entry.status;
  const enabled = status !== "disabled";
  const logo = renderIntegrationLogo(entry.logoKey, "h-6 w-6");

  return (
    <button
      type="button"
      onClick={onClick}
      className={integrationCardRootClassName(
        status === "disabled" ? "disconnected" : status,
      )}
      aria-label={`${entry.label} — ${status === "connected" ? tl("Conectado") : status === "pending" ? tl("Pendente") : tl("Desconectado")}`}
    >
      {/* Logo */}
      <div
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg transition-colors"
        style={{
          background: enabled
            ? `color-mix(in srgb, ${entry.gradientFrom} 18%, var(--surface-elevated) 82%)`
            : "var(--surface-panel-soft)",
        }}
      >
        {logo || <div className="h-6 w-6 rounded bg-[var(--field-bg)]" />}
      </div>

      {/* Text */}
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-semibold text-[var(--text-primary)]">
          {entry.label}
        </div>
        <div className="mt-0.5 truncate text-xs text-[var(--text-quaternary)]">
          {tl(entry.tagline)}
        </div>
      </div>

      {/* Status indicator */}
      <div className="flex shrink-0 items-center">
        <IntegrationCardStatusIndicator
          status={status === "disabled" ? "disconnected" : status}
        />
      </div>
    </button>
  );
}
