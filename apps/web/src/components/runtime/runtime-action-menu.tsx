"use client";

import type { ComponentType } from "react";
import {
  LoaderCircle,
  MoreHorizontal,
  Pin,
  RefreshCcw,
  RotateCcw,
  SquareSlash,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

type RuntimeMenuTone = "neutral" | "warning" | "danger";

type RuntimeRunAction = (
  action: string,
  label: string,
  options?: { confirmMessage?: string; searchParams?: URLSearchParams },
) => void;

interface RuntimeActionMenuProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isPinned: boolean;
  busyAction: string | null;
  onRefresh: () => void;
  runAction: RuntimeRunAction;
}

export function RuntimeActionMenu({
  open,
  onOpenChange,
  isPinned,
  busyAction,
  onRefresh,
  runAction,
}: RuntimeActionMenuProps) {
  const { t } = useAppI18n();
  const pinLabel = isPinned ? t("runtime.room.unpin") : t("runtime.room.pin");

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          selected={open}
          className="h-8 gap-1.5 rounded-[var(--radius-chip)] border-transparent px-2.5 text-[0.8125rem] font-medium text-[var(--text-secondary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)] data-[state=open]:bg-[var(--panel-strong)] data-[state=open]:text-[var(--text-primary)]"
          aria-label={t("runtime.room.moreMenuLabel")}
          aria-haspopup="menu"
          aria-expanded={open}
        >
          <MoreHorizontal className="h-3.5 w-3.5" strokeWidth={1.75} />
          <span className="max-sm:sr-only">{t("runtime.room.more")}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        sideOffset={8}
        className="w-[14.5rem] p-1.5"
        role="menu"
        aria-label={t("runtime.room.moreMenuLabel")}
      >
        <div className="flex flex-col gap-1">
          <RuntimeMenuItem
            icon={RefreshCcw}
            label={t("runtime.room.refresh")}
            onClick={() => {
              onRefresh();
              onOpenChange(false);
            }}
          />
          <RuntimeMenuItem
            icon={RotateCcw}
            label={t("runtime.room.retry")}
            busy={busyAction === "retry"}
            onClick={() => runAction("retry", t("runtime.room.retry"))}
          />
          <RuntimeMenuItem
            icon={RefreshCcw}
            label={t("runtime.room.recover")}
            busy={busyAction === "recover"}
            onClick={() => runAction("recover", t("runtime.room.recover"))}
          />
        </div>

        <RuntimeMenuDivider />

        <RuntimeMenuItem
          icon={Pin}
          label={pinLabel}
          busy={busyAction === "pin" || busyAction === "unpin"}
          onClick={() => runAction(isPinned ? "unpin" : "pin", pinLabel)}
        />

        <RuntimeMenuDivider />

        <div className="flex flex-col gap-1">
          <RuntimeMenuItem
            icon={SquareSlash}
            label={t("runtime.room.cancelExecution")}
            busy={busyAction === "cancel"}
            onClick={() =>
              runAction("cancel", t("runtime.room.cancelExecution"), {
                confirmMessage: t("runtime.room.cancelExecutionConfirm"),
              })
            }
            tone="danger"
          />
          <RuntimeMenuItem
            icon={Trash2}
            label={t("runtime.room.requestCleanup")}
            busy={busyAction === "cleanup"}
            onClick={() =>
              runAction("cleanup", t("runtime.room.requestCleanup"), {
                confirmMessage: t("runtime.room.requestCleanupConfirm"),
              })
            }
            tone="warning"
          />
          <RuntimeMenuItem
            icon={Trash2}
            label={t("runtime.room.forceCleanup")}
            busy={busyAction === "cleanup/force"}
            onClick={() =>
              runAction("cleanup/force", t("runtime.room.forceCleanup"), {
                confirmMessage: t("runtime.room.forceCleanupConfirm"),
              })
            }
            tone="danger"
          />
        </div>
      </PopoverContent>
    </Popover>
  );
}

function RuntimeMenuDivider() {
  return <div className="my-1 h-px bg-[var(--divider-hair)]" aria-hidden="true" />;
}

function RuntimeMenuItem({
  icon: Icon,
  label,
  onClick,
  busy = false,
  tone = "neutral",
}: {
  icon: ComponentType<{ className?: string; strokeWidth?: number }>;
  label: string;
  onClick: () => void;
  busy?: boolean;
  tone?: RuntimeMenuTone;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      disabled={busy}
      onClick={onClick}
      className={cn(
        "flex h-8 w-full items-center gap-2 rounded-[var(--radius-chip)] px-2 text-left text-[13px] font-medium outline-none",
        "transition-[background-color,color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        "focus-visible:bg-[var(--hover-tint)] focus-visible:ring-1 focus-visible:ring-[var(--focus-ring)]",
        "disabled:cursor-progress disabled:opacity-70",
        tone === "danger"
          ? "text-[var(--tone-danger-text)] hover:bg-[var(--tone-danger-bg)]"
          : tone === "warning"
            ? "text-[var(--tone-warning-text)] hover:bg-[var(--tone-warning-bg)]"
            : "text-[var(--text-secondary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]",
      )}
    >
      {busy ? (
        <LoaderCircle className="h-3.5 w-3.5 shrink-0 animate-spin" aria-hidden="true" />
      ) : (
        <Icon className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
      )}
      <span className="truncate">{label}</span>
    </button>
  );
}
