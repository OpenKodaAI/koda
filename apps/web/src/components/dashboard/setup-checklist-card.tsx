"use client";

import Link from "next/link";
import { useCallback, useState, useSyncExternalStore } from "react";
import { ArrowRight, Bot as AgentIcon, Circle, MessageSquare, Plug, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAppI18n } from "@/hooks/use-app-i18n";

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
}

export interface SetupChecklistCardProps {
  snapshot: SetupChecklistSnapshot;
}

export function SetupChecklistCard({ snapshot }: SetupChecklistCardProps) {
  const { t } = useAppI18n();
  const persistedDismissedAt = useSyncExternalStore(subscribeToStorage, readDismissedAt, getServerSnapshot);
  const [forcedDismiss, setForcedDismiss] = useState(false);
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
  const allDone = snapshot.providerReady && snapshot.agentReady && snapshot.telegramReady;
  if (allDone) return null;

  const items = [
    {
      key: "provider",
      label: t("dashboard.checklist.provider"),
      href: "/control-plane/system/models",
      Icon: Plug,
      done: snapshot.providerReady,
    },
    {
      key: "agent",
      label: t("dashboard.checklist.agent"),
      href: "/control-plane",
      Icon: AgentIcon,
      done: snapshot.agentReady,
    },
    {
      key: "telegram",
      label: t("dashboard.checklist.telegram"),
      href: "/control-plane/system/integrations",
      Icon: MessageSquare,
      done: snapshot.telegramReady,
    },
  ];

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
        {items.map(({ key, label, href, Icon, done }) => (
          <li key={key} className="border-t border-[color:var(--divider-hair)] first:border-t-0">
            <Link
              href={href}
              className="group flex items-center gap-3 px-1.5 py-2 text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
            >
              <span
                className={`inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${
                  done
                    ? "bg-[var(--tone-success-bg-strong)] text-white"
                    : "bg-[var(--surface-hover)] text-[var(--text-tertiary)]"
                }`}
              >
                {done ? <Icon className="h-3.5 w-3.5" /> : <Circle className="h-3 w-3" />}
              </span>
              <span className="flex-1 text-[13px]">{label}</span>
              <ArrowRight className="icon-xs text-[var(--text-quaternary)] transition-transform group-hover:translate-x-0.5" />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
