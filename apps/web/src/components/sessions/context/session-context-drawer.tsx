"use client";

import { useCallback, useState } from "react";
import { ChevronLeft } from "lucide-react";
import { Drawer } from "@/components/ui/drawer";
import { Button } from "@/components/ui/button";
import { ArtifactViewer } from "@/components/sessions/artifacts/artifact-viewer";
import { executionArtifactToArtifactDetail } from "@/components/sessions/artifacts/artifact-detail";
import { SessionContextPanel } from "./session-context-panel";
import type { SessionArtifactItem } from "./context-artifacts";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { truncateText } from "@/lib/utils";
import type { ArtifactDetail } from "@/lib/contracts/artifacts";
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
  const [activeArtifact, setActiveArtifact] = useState<ArtifactDetail | null>(null);

  const handleOpenChange = useCallback(
    (next: boolean) => {
      // Reset the inner state machine when the drawer closes — handled in the
      // change callback rather than an effect to avoid setState-in-effect.
      if (!next) setActiveArtifact(null);
      onOpenChange(next);
    },
    [onOpenChange],
  );

  const sessionAgentId =
    summary?.bot_id ?? (detail?.summary as { bot_id?: string | null })?.bot_id ?? null;

  const handleOpenArtifact = useCallback(
    (item: SessionArtifactItem) => {
      const artifact = executionArtifactToArtifactDetail(item, sessionAgentId, item.activityAt);
      if (artifact) setActiveArtifact(artifact);
    },
    [sessionAgentId],
  );

  const baseTitle = summary?.name?.trim()
    ? summary.name.trim()
    : summary
      ? truncateText(summary.session_id, 24)
      : t("chat.header.viewDetails", { defaultValue: "Session details" });

  const title = activeArtifact
    ? truncateText(activeArtifact.label ?? activeArtifact.id, 32)
    : baseTitle;

  return (
    <Drawer
      open={open}
      onOpenChange={handleOpenChange}
      title={title}
      width="min(560px, 92vw)"
    >
      {activeArtifact ? (
        <div className="flex flex-col">
          <div className="flex items-center gap-1 px-3 py-2 border-b border-[color:var(--divider-hair)]">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setActiveArtifact(null)}
            >
              <ChevronLeft className="icon-xs" strokeWidth={1.75} aria-hidden />
              {t("common.back", { defaultValue: "Back" })}
            </Button>
          </div>
          <ArtifactViewer
            artifact={activeArtifact}
            showHeader={false}
            onClose={() => setActiveArtifact(null)}
          />
        </div>
      ) : (
        <SessionContextPanel
          detail={detail}
          summary={summary}
          onOpenExecution={onOpenExecution}
          onOpenArtifact={handleOpenArtifact}
        />
      )}
    </Drawer>
  );
}
