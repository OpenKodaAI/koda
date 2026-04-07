"use client";

import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";
import type { SessionDetail } from "@/lib/types";
import {
  useAnimatedPresence,
  useBodyScrollLock,
  useEscapeToClose,
} from "@/hooks/use-animated-presence";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { SessionDetailView } from "./session-detail-view";

interface SessionDetailDrawerProps {
  detail: SessionDetail | null;
  loading?: boolean;
  error?: string | null;
  isOpen: boolean;
  onClose: () => void;
}

export function SessionDetailDrawer({
  detail,
  loading = false,
  error,
  isOpen,
  onClose,
}: SessionDetailDrawerProps) {
  const { t } = useAppI18n();
  const presence = useAnimatedPresence(
    isOpen && (Boolean(detail) || loading || Boolean(error)),
    { detail, loading, error },
    { duration: 180 }
  );

  useBodyScrollLock(presence.shouldRender);
  useEscapeToClose(presence.shouldRender, onClose);

  if (!presence.shouldRender) {
    return null;
  }

  if (typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <>
      <div
        className={cn(
          "app-overlay-backdrop",
          presence.isVisible ? "opacity-100" : "pointer-events-none opacity-0"
        )}
        onClick={onClose}
      />
      <div
        className={cn(
          "fixed inset-y-0 right-0 z-[70] w-full transition-opacity duration-150 ease-out",
          presence.isVisible
            ? "opacity-100"
            : "pointer-events-none opacity-0"
        )}
        role="dialog"
        aria-modal="true"
        aria-label={t("sessions.detail.dialogTitle")}
      >
        <div className="app-drawer-panel ml-auto flex h-full w-full flex-col overflow-hidden">
          <SessionDetailView
            key={`${presence.renderedValue.detail?.summary.bot_id ?? "unknown"}:${presence.renderedValue.detail?.summary.session_id ?? "empty"}`}
            detail={presence.renderedValue.detail}
            loading={presence.isVisible ? loading : presence.renderedValue.loading}
            error={presence.isVisible ? error : presence.renderedValue.error}
            onClose={onClose}
          />
        </div>
      </div>
    </>,
    document.body
  );
}
