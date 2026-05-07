"use client";

/**
 * ConnectIntegrationModal — opens when the user clicks "Conectar" on a
 * non-OAuth integration. Wraps `ConnectIntegrationPanel` inside the canonical
 * glass-blur dialog so the credential form / JSON option lives in a focused
 * overlay rather than as a fixed panel at the bottom of the integration page.
 */

import { useRef } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  useAnimatedPresence,
  useBodyScrollLock,
  useEscapeToClose,
} from "@/hooks/use-animated-presence";
import { renderIntegrationLogo } from "@/components/control-plane/system/integrations/integration-logos";

import {
  ConnectIntegrationPanel,
  type ConnectIntegrationPanelHandle,
} from "./connect-integration-panel";
import type { AgentIntegrationEntry } from "@/hooks/use-agent-integration-permissions";
import type { McpOAuthStatus } from "@/lib/control-plane";

export type ConnectIntegrationModalProps = {
  open: boolean;
  entry: AgentIntegrationEntry;
  oauthStatus?: McpOAuthStatus;
  onSubmitForm: (envValues: Record<string, string>) => Promise<void>;
  onSubmitJson?: (rawJson: string) => Promise<void>;
  onClose: () => void;
};

export function ConnectIntegrationModal({
  open,
  entry,
  oauthStatus,
  onSubmitForm,
  onSubmitJson,
  onClose,
}: ConnectIntegrationModalProps) {
  const { tl } = useAppI18n();
  const presence = useAnimatedPresence(open, null, { duration: 200 });
  const panelRef = useRef<ConnectIntegrationPanelHandle | null>(null);

  useBodyScrollLock(presence.shouldRender);
  useEscapeToClose(presence.shouldRender, onClose);

  if (!presence.shouldRender) return null;
  if (typeof document === "undefined") return null;

  const handleSubmitForm = async (envValues: Record<string, string>) => {
    await onSubmitForm(envValues);
    onClose();
  };

  const handleSubmitJson = onSubmitJson
    ? async (raw: string) => {
        await onSubmitJson(raw);
        onClose();
      }
    : undefined;

  return createPortal(
    <>
      <div
        className="app-overlay-backdrop app-overlay-anim z-[70]"
        data-visible={presence.isVisible}
        data-state={presence.dataState}
        onClick={onClose}
        aria-hidden="true"
      />
      <div className="app-modal-frame z-[80] p-4">
        <div
          className="app-modal-panel app-modal-anim relative flex w-full max-w-lg max-h-[calc(100vh-4rem)] flex-col"
          data-visible={presence.isVisible}
          data-state={presence.dataState}
          role="dialog"
          aria-modal="true"
          aria-labelledby="connect-integration-modal-title"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            onClick={onClose}
            className="app-surface-close"
            aria-label={tl("Fechar modal")}
          >
            <X className="h-4 w-4" />
          </button>

          <div className="flex items-center gap-3 border-b border-[var(--border-subtle)] px-6 py-4 pr-14">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--panel-soft)]">
              {renderIntegrationLogo(entry.logoKey, "h-5 w-5")}
            </div>
            <h3
              id="connect-integration-modal-title"
              className="text-base font-semibold text-[var(--text-primary)]"
            >
              {tl("Conectar a {{name}}", { name: entry.label })}
            </h3>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-5">
            <ConnectIntegrationPanel
              ref={panelRef}
              entry={entry}
              oauthStatus={oauthStatus}
              onSubmitForm={handleSubmitForm}
              onSubmitJson={handleSubmitJson}
            />
          </div>

          <div className="flex justify-end gap-2 border-t border-[var(--border-subtle)] px-6 py-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-[var(--border-subtle)] px-4 py-1.5 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)]"
            >
              {tl("Cancelar")}
            </button>
            <button
              type="button"
              onClick={() => panelRef.current?.submit()}
              className="inline-flex items-center gap-1.5 rounded-lg px-4 py-1.5 text-xs font-semibold text-[var(--interactive-active-text)] transition-all"
              style={{
                background:
                  "linear-gradient(180deg, var(--interactive-active-top), var(--interactive-active-bottom))",
                border: "1px solid var(--interactive-active-border)",
              }}
            >
              {tl("Conectar")}
            </button>
          </div>
        </div>
      </div>
    </>,
    document.body,
  );
}
