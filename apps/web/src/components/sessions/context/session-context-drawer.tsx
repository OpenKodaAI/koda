"use client";

import { Drawer } from "@/components/ui/drawer";
import { SessionContextPanel } from "./session-context-panel";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { truncateText } from "@/lib/utils";
import type { SessionDetail, SessionSummary } from "@/lib/types";

interface SessionContextDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  detail: SessionDetail | null;
  summary: SessionSummary | null;
  onOpenExecution?: (taskId: number, agentId: string | null) => void;
}

export function SessionContextDrawer({
  open,
  onOpenChange,
  detail,
  summary,
  onOpenExecution,
}: SessionContextDrawerProps) {
  const { t } = useAppI18n();
  const title = summary?.name?.trim()
    ? summary.name.trim()
    : summary
      ? truncateText(summary.session_id, 24)
      : t("chat.header.viewDetails", { defaultValue: "Session details" });

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      width="min(400px, 92vw)"
    >
      <SessionContextPanel
        detail={detail}
        summary={summary}
        onOpenExecution={onOpenExecution}
      />
    </Drawer>
  );
}
