"use client";

import Link from "next/link";
import { useCallback, useState, useSyncExternalStore } from "react";
import { ArrowRight, Bot as AgentIcon, MessageSquare, Play, Plug, Route, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { requestJson } from "@/lib/http-client";

const DISMISS_KEY = "koda.dashboard.setupChecklistDismissedAt";

function subscribeToStorage(notify: () => void) {
  if (typeof window === "undefined") return () => undefined;
  window.addEventListener("storage", notify);
  return () => window.removeEventListener("storage", notify);
}

function readDismissedAt(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(DISMISS_KEY);
  } catch {
    return null;
  }
}

function getServerSnapshot(): string | null {
  return null;
}

export interface SetupChecklistSnapshot {
  providerReady: boolean;
  agentReady: boolean;
  telegramReady: boolean;
  channelReady: boolean;
  firstTaskReady: boolean;
  firstTraceReady: boolean;
  readinessStatus: "passed" | "warning" | "failed" | "pending";
  primaryAgentId: string;
  readinessActions: Array<{ check: string; label: string; href: string }>;
}

export interface SetupChecklistCardProps {
  snapshot: SetupChecklistSnapshot;
}

export function SetupChecklistCard({ snapshot }: SetupChecklistCardProps) {
  const { t } = useAppI18n();
  const persistedDismissedAt = useSyncExternalStore(subscribeToStorage, readDismissedAt, getServerSnapshot);
  const [forcedDismiss, setForcedDismiss] = useState(false);
  const [creatingFirstTask, setCreatingFirstTask] = useState(false);
  const [firstTaskError, setFirstTaskError] = useState<string | null>(null);
  const dismissed = forcedDismiss || Boolean(persistedDismissedAt);

  const handleDismiss = useCallback(() => {
    try {
      window.localStorage.setItem(DISMISS_KEY, new Date().toISOString());
    } catch {
      // Best-effort.
    }
    setForcedDismiss(true);
  }, []);

  if (dismissed) return null;
  const allDone =
    snapshot.providerReady &&
    snapshot.agentReady &&
    snapshot.telegramReady &&
    snapshot.channelReady &&
    snapshot.firstTaskReady &&
    snapshot.firstTraceReady;
  if (allDone) return null;

  const items = [
    {
      key: "provider",
      label: t("dashboard.checklist.provider"),
      href: "/control-plane/system/models",
      Icon: Plug,
      iconTone:
        "border-[color:var(--tone-info-border)] bg-[color:var(--tone-info-bg)] text-[color:var(--tone-info-text)]",
    },
    {
      key: "agent",
      label: t("dashboard.checklist.agent"),
      href: "/control-plane",
      Icon: AgentIcon,
      iconTone:
        "border-[color:var(--tone-success-border)] bg-[color:var(--tone-success-bg)] text-[color:var(--tone-success-text)]",
    },
    {
      key: "telegram",
      label: t("dashboard.checklist.telegram"),
      href: "/control-plane/system/integrations",
      Icon: MessageSquare,
      iconTone:
        "border-[color:var(--tone-retry-border)] bg-[color:var(--tone-retry-bg)] text-[color:var(--tone-retry-text)]",
    },
    {
      key: "channel",
      label: "Pair Telegram sender",
      href: "/control-plane",
      Icon: Route,
      iconTone:
        "border-[color:var(--tone-warning-border)] bg-[color:var(--tone-warning-bg)] text-[color:var(--tone-warning-text)]",
    },
    {
      key: "firstTask",
      label: "Run first task",
      href: "/",
      Icon: Play,
      iconTone:
        "border-[color:var(--tone-success-border)] bg-[color:var(--tone-success-bg)] text-[color:var(--tone-success-text)]",
    },
    {
      key: "firstTrace",
      label: "Open first trace",
      href: "/executions",
      Icon: ArrowRight,
      iconTone:
        "border-[color:var(--tone-info-border)] bg-[color:var(--tone-info-bg)] text-[color:var(--tone-info-text)]",
    },
  ];

  async function createFirstTask() {
    setCreatingFirstTask(true);
    setFirstTaskError(null);
    try {
      await requestJson("/api/control-plane/onboarding/first-task", {
        method: "POST",
        body: JSON.stringify({
          agent_id: snapshot.primaryAgentId || undefined,
        }),
      });
    } catch (error) {
      setFirstTaskError(error instanceof Error ? error.message : "Could not create first task.");
    } finally {
      setCreatingFirstTask(false);
    }
  }

  return (
    <section
      aria-label={t("dashboard.checklist.title")}
      className="relative flex flex-col gap-3 rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-4 py-3.5"
    >
      <header className="flex items-start justify-between gap-3">
        <div className="flex flex-col">
          <h2 className="m-0 text-[var(--font-size-sm)] font-medium text-[var(--text-primary)]">
            {t("dashboard.checklist.title")}
          </h2>
          <p className="m-0 text-[12px] text-[var(--text-tertiary)]">
            {t("dashboard.checklist.subtitle")}
          </p>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-label={t("dashboard.checklist.dismiss")}
          onClick={handleDismiss}
          className="h-7 w-7 p-0"
        >
          <X className="icon-sm" strokeWidth={1.75} />
        </Button>
      </header>
      <ul className="flex flex-col gap-0.5">
        {items.map(({ key, label, href, Icon, iconTone }) => (
          <li key={key} className="border-t border-[color:var(--divider-hair)] first:border-t-0">
            <Link
              href={href}
              className="group flex items-center gap-3 px-1.5 py-2 text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
            >
              <span
                className={`inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border ${iconTone}`}
              >
                <Icon className="h-3.5 w-3.5" strokeWidth={1.75} />
              </span>
              <span className="flex-1 text-[13px]">{label}</span>
              <ArrowRight className="icon-xs text-[var(--text-quaternary)] transition-transform group-hover:translate-x-0.5" />
            </Link>
          </li>
        ))}
      </ul>
      {!snapshot.firstTaskReady && snapshot.agentReady && (
        <div className="flex items-center justify-between gap-3 border-t border-[color:var(--divider-hair)] pt-3">
          <div className="min-w-0 text-[12px] text-[var(--text-tertiary)]">
            {firstTaskError ?? "Create a safe dashboard task to verify the runtime path."}
          </div>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={createFirstTask}
            disabled={creatingFirstTask}
            className="shrink-0"
          >
            {creatingFirstTask ? "Creating" : "Run"}
          </Button>
        </div>
      )}
    </section>
  );
}
