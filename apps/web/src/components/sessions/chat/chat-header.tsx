"use client";

import { Info, PanelLeft } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { SessionControls } from "@/components/sessions/chat/session-controls";
import { cn } from "@/lib/utils";

interface ChatHeaderProps {
  title: string;
  agentId?: string | null;
  sessionId?: string | null;
  onOpenContext?: () => void;
  onOpenRail?: () => void;
  showRailToggle?: boolean;
  showContextToggle?: boolean;
  scrolled?: boolean;
  sessionActive?: boolean;
  sessionPaused?: boolean;
}

export function ChatHeader({
  title,
  agentId,
  sessionId,
  onOpenContext,
  onOpenRail,
  showRailToggle = false,
  showContextToggle = false,
  scrolled = false,
  sessionActive = false,
  sessionPaused = false,
}: ChatHeaderProps) {
  const { t } = useAppI18n();
  const { agents } = useAgentCatalog();
  const agent = agentId ? agents.find((entry) => entry.id === agentId) : null;

  return (
    <header
      data-scrolled={scrolled ? "true" : "false"}
      className={cn(
        "sticky top-0 z-10 flex h-12 shrink-0 items-center justify-between",
        "border-b border-transparent bg-[var(--canvas)]/95 px-5 backdrop-blur-[6px]",
        "transition-[border-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        scrolled && "border-[color:var(--divider-hair)]",
      )}
    >
      <div className="flex min-w-0 items-center gap-2">
        {showRailToggle ? (
          <button
            type="button"
            onClick={onOpenRail}
            aria-label={t("chat.rail.openLabel", { defaultValue: "Open conversations" })}
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-panel-sm)] text-[var(--text-tertiary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)] md:hidden"
          >
            <PanelLeft className="icon-sm" strokeWidth={1.75} aria-hidden />
          </button>
        ) : null}
        <h2 className="m-0 truncate text-[0.875rem] font-medium text-[var(--text-primary)]">
          {title}
        </h2>
        {agent ? (
          <span className="hidden items-center gap-1.5 text-[0.6875rem] text-[var(--text-tertiary)] sm:inline-flex">
            <span
              aria-hidden
              className="h-1.5 w-1.5 rounded-full"
              style={{ background: agent.color ?? "var(--accent)" }}
            />
            <span className="truncate max-w-[140px]">{agent.label || agent.id}</span>
          </span>
        ) : null}
      </div>
      <div className="flex items-center gap-2">
        <SessionControls
          agentId={agentId ?? null}
          sessionId={sessionId ?? null}
          active={sessionActive}
          paused={sessionPaused}
        />
        {showContextToggle ? (
          <button
            type="button"
            onClick={onOpenContext}
            aria-label={t("chat.header.viewDetails", { defaultValue: "Session details" })}
            className="inline-flex h-8 w-8 items-center justify-center rounded-[var(--radius-panel-sm)] text-[var(--text-tertiary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]"
          >
            <Info className="icon-sm" strokeWidth={1.75} aria-hidden />
          </button>
        ) : null}
      </div>
    </header>
  );
}
