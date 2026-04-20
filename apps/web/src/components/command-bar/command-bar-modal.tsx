"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { useAgentStats } from "@/hooks/use-agent-stats";
import {
  usePendingApprovalsCatalog,
  useSkillsCatalog,
  useToolsCatalog,
} from "@/hooks/use-command-catalog";
import { CommandBar } from "./command-bar";
import type { CommandBarContext } from "./command-registry";

export function CommandBarModal() {
  const { t } = useAppI18n();
  const { agents } = useAgentCatalog();
  const router = useRouter();
  const { stats } = useAgentStats();
  const [open, setOpen] = useState(false);

  const primaryAgentId = agents[0]?.id ?? null;
  const skills = useSkillsCatalog(open);
  const tools = useToolsCatalog(primaryAgentId, open);
  const pendingApprovals = usePendingApprovalsCatalog(primaryAgentId, open);

  const openModal = useCallback(() => setOpen(true), []);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const key = event.key?.toLowerCase();
      if (key !== "k") return;
      if (!(event.metaKey || event.ctrlKey)) return;

      const target = event.target as HTMLElement | null;
      if (target) {
        const tag = target.tagName.toLowerCase();
        if (tag === "input" || tag === "textarea" || target.isContentEditable) {
          if (!event.metaKey && !event.ctrlKey) return;
        }
      }
      event.preventDefault();
      openModal();
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [openModal]);

  const ctx = useMemo<CommandBarContext>(
    () => ({
      agents,
      stats,
      skills,
      tools,
      pendingApprovals,
      router: { push: router.push.bind(router) },
      t,
      openAgentDetail: (agentId: string) =>
        router.push(`/control-plane/agents/${encodeURIComponent(agentId)}`),
      openSession: (agentId: string, sessionId: string) =>
        router.push(
          `/sessions?agent=${encodeURIComponent(agentId)}&session=${encodeURIComponent(sessionId)}`,
        ),
    }),
    [agents, router, stats, skills, tools, pendingApprovals, t],
  );

  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay
          className={cn(
            "fixed inset-0 z-[80] bg-[rgba(0,0,0,0.55)] backdrop-blur-[6px]",
            "data-[state=open]:animate-in data-[state=closed]:animate-out",
            "data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0",
          )}
        />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          onOpenAutoFocus={(event) => {
            // Prevent Radix's default focus behavior from calling
            // element.focus() without preventScroll — that default call is
            // what was yanking the home-screen content upward when the
            // command bar appears. We re-focus the input ourselves inside
            // the CommandBar component with preventScroll: true.
            event.preventDefault();
          }}
          className={cn(
            "app-modal-panel !fixed left-1/2 top-[18vh] z-[81] flex max-h-[72vh] w-[min(600px,92vw)] -translate-x-1/2 flex-col outline-none",
            "data-[state=open]:animate-in data-[state=closed]:animate-out",
            "data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0",
            "data-[state=open]:zoom-in-95 data-[state=closed]:zoom-out-95",
          )}
        >
          <DialogPrimitive.Title className="sr-only">
            {t("commandBar.modalTitle")}
          </DialogPrimitive.Title>
          <CommandBar
            ctx={ctx}
            mode="modal"
            placeholder={t("commandBar.placeholder")}
            emptyState={t("commandBar.emptyState")}
            autoFocus
            onAfterExecute={() => setOpen(false)}
          />
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
