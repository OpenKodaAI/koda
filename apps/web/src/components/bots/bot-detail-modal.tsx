"use client";

import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";
import { BotSwitcher } from "@/components/layout/bot-switcher";
import { useBotCatalog } from "@/components/providers/bot-catalog-provider";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  useAnimatedPresence,
  useBodyScrollLock,
  useEscapeToClose,
} from "@/hooks/use-animated-presence";
import { BotDetailContent } from "./bot-detail-content";

interface BotDetailModalProps {
  botId: string | null;
  isOpen: boolean;
  onClose: () => void;
  onBotChange: (botId: string) => void;
}

export function BotDetailModal({
  botId,
  isOpen,
  onClose,
  onBotChange,
}: BotDetailModalProps) {
  const { botDisplayMap } = useBotCatalog();
  const { tl } = useAppI18n();
  const presence = useAnimatedPresence(isOpen && Boolean(botId), { botId }, { duration: 320 });
  const renderedBotId = presence.renderedValue.botId ?? botId;
  const botDisplay = renderedBotId ? botDisplayMap[renderedBotId] : null;

  useBodyScrollLock(presence.shouldRender);
  useEscapeToClose(presence.shouldRender, onClose);

  if (!presence.shouldRender || !renderedBotId || !botDisplay) {
    return null;
  }

  if (typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <>
      <div
        className={cn(
          "app-overlay-backdrop transition-opacity duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
          presence.isVisible ? "opacity-100" : "pointer-events-none opacity-0"
        )}
        onClick={onClose}
      />
      <div className="app-modal-frame z-[70] items-stretch p-3 sm:p-5 lg:p-6 xl:p-7">
        <div
          role="dialog"
          aria-modal="true"
          aria-label={tl("Resumo do bot {{name}}", { name: botDisplay.label })}
          className={cn(
            "app-modal-panel relative flex h-full w-full max-w-[1760px] flex-col overflow-hidden transition-opacity duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
            presence.isVisible
              ? "opacity-100"
              : "pointer-events-none opacity-0"
          )}
          style={{
            boxShadow: `0 36px 140px rgba(0,0,0,0.55), inset 0 1px 0 ${botDisplay.color}12`,
          }}
          onClick={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            onClick={onClose}
            className="app-surface-close"
            aria-label={tl("Fechar modal")}
          >
            <X className="h-4 w-4" />
          </button>

          <div className="border-b border-[rgba(255,255,255,0.07)] bg-[rgba(10,10,10,0.94)] px-5 py-4 pr-14 backdrop-blur-xl sm:px-6 sm:pr-16 lg:px-7">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div className="min-w-0">
                <span className="app-card-row__eyebrow">{tl("Bot")}</span>
                <h2 className="mt-2 text-[1.45rem] font-semibold tracking-[-0.06em] text-[var(--text-primary)] sm:text-[1.65rem]">
                  {botDisplay.label}
                </h2>
              </div>

              <div className="flex min-w-0 flex-col gap-3 xl:items-end">
                <BotSwitcher
                  activeBotId={renderedBotId}
                  onBotChange={(nextBotId) => {
                    if (nextBotId) onBotChange(nextBotId);
                  }}
                  showAll={false}
                />
              </div>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-5 sm:py-5 lg:px-6 lg:py-6">
            <BotDetailContent key={renderedBotId} botId={renderedBotId} />
          </div>
        </div>
      </div>
    </>,
    document.body
  );
}
