"use client";

import { PanelLeft, PanelRight } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { SessionControls } from "@/components/sessions/chat/session-controls";
import { AvatarGroupWithTooltips } from "@/components/ui/avatar-group-with-tooltip";
import { cn } from "@/lib/utils";

interface ChatHeaderProps {
  title: string;
  agentId?: string | null;
  sessionId?: string | null;
  onOpenRail?: () => void;
  showRailToggle?: boolean;
  showContextToggle?: boolean;
  contextPanelOpen?: boolean;
  onToggleContextPanel?: () => void;
  scrolled?: boolean;
  sessionActive?: boolean;
  sessionPaused?: boolean;
}

export function ChatHeader({
  title,
  agentId,
  sessionId,
  onOpenRail,
  showRailToggle = false,
  showContextToggle = false,
  contextPanelOpen = false,
  onToggleContextPanel,
  scrolled = false,
  sessionActive = false,
  sessionPaused = false,
}: ChatHeaderProps) {
  const { t } = useAppI18n();
  const { agents } = useAgentCatalog();
  const agent = agentId ? agents.find((entry) => entry.id === agentId) : null;
  const agentAvatar = agent
    ? [
        {
          id: agent.id,
          name: agent.label || agent.id,
          color: agent.color,
        },
      ]
    : [];

  return (
    <header
      data-scrolled={scrolled ? "true" : "false"}
      className={cn(
        "sticky top-0 z-10 flex h-14 shrink-0 items-center justify-between",
        "border-b border-transparent bg-[var(--canvas)]/95 px-5 backdrop-blur-[6px] lg:px-6",
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
        <h2 className="m-0 max-w-[min(52vw,560px)] truncate text-[0.875rem] font-medium text-[var(--text-primary)]">
          {title}
        </h2>
      </div>
      <div className="flex items-center gap-2">
        {agent ? (
          <AvatarGroupWithTooltips
            avatars={agentAvatar}
            maxVisible={1}
            size="xs"
            showInitials={false}
            ariaLabel={t("chat.header.activeAgent", { defaultValue: "Active agent" })}
            className="hidden sm:inline-flex"
          />
        ) : null}
        {showContextToggle ? (
          <button
            type="button"
            onClick={onToggleContextPanel}
            aria-label={
              contextPanelOpen
                ? t("sessions.context.collapse", { defaultValue: "Collapse panel" })
                : t("sessions.context.expand", { defaultValue: "Expand panel" })
            }
            aria-pressed={contextPanelOpen}
            className={cn(
              "hidden h-8 w-8 items-center justify-center rounded-[var(--radius-panel-sm)] lg:inline-flex",
              "text-[var(--text-tertiary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]",
              contextPanelOpen && "bg-[var(--panel-soft)] text-[var(--text-primary)]",
            )}
          >
            <PanelRight className="icon-sm" strokeWidth={1.75} aria-hidden />
          </button>
        ) : null}
        <SessionControls
          agentId={agentId ?? null}
          sessionId={sessionId ?? null}
          active={sessionActive}
          paused={sessionPaused}
        />
      </div>
    </header>
  );
}
