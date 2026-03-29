"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { startTransition, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowUpRight,
  ChevronRight,
  FileText,
  Search,
} from "lucide-react";
import { ActionButton } from "@/components/ui/action-button";
import { tourAnchor } from "@/components/tour/tour-attrs";
import { useAppTour } from "@/hooks/use-app-tour";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type { AppTranslator } from "@/lib/i18n";
import { getTourChapterForPathname } from "@/lib/tour";
import { cn } from "@/lib/utils";

type TopbarPanelId = "docs" | "ask" | "files" | "notifications" | null;

type ShortcutEntry = {
  eyebrow: string;
  title: string;
  description: string;
  href: string;
};

type FileEntry = {
  name: string;
  detail: string;
  href: string;
  updatedAt: string;
};

type NotificationEntry = {
  section: string;
  title: string;
  description: string;
  timestamp: string;
  href: string;
};

function buildDocEntries(t: AppTranslator): ShortcutEntry[] {
  return [
    {
      eyebrow: t("topbar.docs.entries.dailyOps.eyebrow"),
      title: t("topbar.docs.entries.dailyOps.title"),
      description: t("topbar.docs.entries.dailyOps.description"),
      href: "/executions",
    },
    {
      eyebrow: t("topbar.docs.entries.governance.eyebrow"),
      title: t("topbar.docs.entries.governance.title"),
      description: t("topbar.docs.entries.governance.description"),
      href: "/control-plane/system",
    },
    {
      eyebrow: t("topbar.docs.entries.memory.eyebrow"),
      title: t("topbar.docs.entries.memory.title"),
      description: t("topbar.docs.entries.memory.description"),
      href: "/memory",
    },
  ];
}

function buildFileEntries(t: AppTranslator): FileEntry[] {
  return [
    {
      name: "runtime-handbook.md",
      detail: t("topbar.files.entries.runtime.detail"),
      href: "/runtime",
      updatedAt: t("topbar.files.entries.runtime.updatedAt"),
    },
    {
      name: "governance-catalog.json",
      detail: t("topbar.files.entries.governance.detail"),
      href: "/control-plane/system",
      updatedAt: t("topbar.files.entries.governance.updatedAt"),
    },
    {
      name: "memory-curation-notes.md",
      detail: t("topbar.files.entries.memory.detail"),
      href: "/memory",
      updatedAt: t("topbar.files.entries.memory.updatedAt"),
    },
    {
      name: "cost-review.csv",
      detail: t("topbar.files.entries.costs.detail"),
      href: "/costs",
      updatedAt: t("topbar.files.entries.costs.updatedAt"),
    },
  ];
}

function buildNotificationEntries(t: AppTranslator): NotificationEntry[] {
  return [
    {
      section: t("topbar.notifications.entries.sessions.section"),
      title: t("topbar.notifications.entries.sessions.title"),
      description: t("topbar.notifications.entries.sessions.description"),
      timestamp: t("topbar.notifications.entries.sessions.timestamp"),
      href: "/sessions",
    },
    {
      section: t("topbar.notifications.entries.memory.section"),
      title: t("topbar.notifications.entries.memory.title"),
      description: t("topbar.notifications.entries.memory.description"),
      timestamp: t("topbar.notifications.entries.memory.timestamp"),
      href: "/memory",
    },
    {
      section: t("topbar.notifications.entries.system.section"),
      title: t("topbar.notifications.entries.system.title"),
      description: t("topbar.notifications.entries.system.description"),
      timestamp: t("topbar.notifications.entries.system.timestamp"),
      href: "/control-plane/system",
    },
  ];
}

function buildAskReply(prompt: string, t: AppTranslator) {
  const query = prompt.toLowerCase();

  if (query.includes("falha") || query.includes("fila") || query.includes("erro")) {
    return t("topbar.ask.replies.failures");
  }

  if (query.includes("custo") || query.includes("gasto") || query.includes("consumo")) {
    return t("topbar.ask.replies.cost");
  }

  if (query.includes("rotina") || query.includes("agendamento") || query.includes("cron")) {
    return t("topbar.ask.replies.schedules");
  }

  if (query.includes("sess") || query.includes("chat") || query.includes("conversa")) {
    return t("topbar.ask.replies.sessions");
  }

  return t("topbar.ask.replies.fallback");
}

function TopbarActionTrigger({
  label,
  asset,
  active,
  iconOnly = false,
  highlight = false,
  anchor,
  onClick,
}: {
  label: string;
  asset: string;
  active: boolean;
  iconOnly?: boolean;
  highlight?: boolean;
  anchor: string;
  onClick: () => void;
}) {
  const icon = (
    <span className="relative flex items-center justify-center">
      <span
        className="workspace-topbar__asset-icon"
        style={
          {
            display: "inline-block",
            width: 16,
            height: 16,
            backgroundColor: "currentColor",
            WebkitMaskImage: `url(${asset})`,
            WebkitMaskPosition: "center",
            WebkitMaskRepeat: "no-repeat",
            WebkitMaskSize: "contain",
            maskImage: `url(${asset})`,
            maskPosition: "center",
            maskRepeat: "no-repeat",
            maskSize: "contain",
          } as CSSProperties
        }
        aria-hidden="true"
      />
      {highlight ? <span className="workspace-topbar__tool-indicator" aria-hidden="true" /> : null}
    </span>
  );

  return (
    <ActionButton
      type="button"
      className={cn(
        "workspace-topbar__tool",
        active && "workspace-topbar__tool--active",
      )}
      onClick={onClick}
      aria-expanded={active}
      aria-haspopup="dialog"
      aria-label={label}
      size={iconOnly ? "icon" : "md"}
      {...tourAnchor(anchor)}
    >
      {icon}
      {!iconOnly ? label : null}
    </ActionButton>
  );
}

export function WorkspaceTopbarActions() {
  const pathname = usePathname();
  const { t } = useAppI18n();
  const { restart, resume, openChapter, status } = useAppTour();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const askTimeoutRef = useRef<number | null>(null);
  const [openPanel, setOpenPanel] = useState<TopbarPanelId>(null);
  const [askPrompt, setAskPrompt] = useState("");
  const [askLoading, setAskLoading] = useState(false);
  const [askReply, setAskReply] = useState<string>(
    t("topbar.ask.initialReply"),
  );
  const [panelPosition, setPanelPosition] = useState<{
    top: number;
    left: number;
    width: number;
    maxHeight: number;
  } | null>(null);
  const docEntries = useMemo(() => buildDocEntries(t), [t]);
  const fileEntries = useMemo(() => buildFileEntries(t), [t]);
  const notificationEntries = useMemo(() => buildNotificationEntries(t), [t]);
  const askSuggestions = useMemo(
    () => [
      t("topbar.ask.suggestions.failures"),
      t("topbar.ask.suggestions.cost"),
      t("topbar.ask.suggestions.schedules"),
    ],
    [t],
  );

  useEffect(() => {
    setAskReply(t("topbar.ask.initialReply"));
  }, [t]);

  useEffect(() => {
    return () => {
      if (askTimeoutRef.current) {
        window.clearTimeout(askTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!openPanel) return;

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!rootRef.current?.contains(target) && !panelRef.current?.contains(target)) {
        setOpenPanel(null);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpenPanel(null);
      }
    };

    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [openPanel]);

  useLayoutEffect(() => {
    if (!openPanel || !rootRef.current) return;

    const updatePosition = () => {
      if (!rootRef.current) return;

      const rect = rootRef.current.getBoundingClientRect();
      const viewportPadding = 12;
      const width = Math.min(
        openPanel === "ask" ? 416 : 384,
        window.innerWidth - viewportPadding * 2,
      );
      const left = Math.min(
        Math.max(rect.right - width, viewportPadding),
        window.innerWidth - viewportPadding - width,
      );
      const top = rect.bottom + 12;
      const maxHeight = Math.max(220, window.innerHeight - top - viewportPadding);

      setPanelPosition({
        top,
        left,
        width,
        maxHeight,
      });
    };

    const frame = window.requestAnimationFrame(updatePosition);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);

    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [openPanel]);

  const handleAskSubmit = (prompt?: string) => {
    const nextPrompt = (prompt ?? askPrompt).trim();
    if (!nextPrompt) return;

    if (askTimeoutRef.current) {
      window.clearTimeout(askTimeoutRef.current);
    }

    setOpenPanel("ask");
    setAskLoading(true);
    setAskPrompt(nextPrompt);

    askTimeoutRef.current = window.setTimeout(() => {
      startTransition(() => {
        setAskReply(buildAskReply(nextPrompt, t));
        setAskLoading(false);
      });
    }, 560);
  };

  const activePanelWidthClass =
    openPanel === "ask"
      ? "workspace-topbar__panel--medium"
      : "workspace-topbar__panel--default";

  const handleTourShortcut = useCallback(() => {
    if (status === "running") {
      resume();
      setOpenPanel(null);
      return;
    }

    if (pathname === "/") {
      restart();
      setOpenPanel(null);
      return;
    }

    const chapterId = getTourChapterForPathname(pathname);
    if (chapterId) {
      openChapter(chapterId);
    } else {
      restart();
    }
    setOpenPanel(null);
  }, [openChapter, pathname, restart, resume, status]);

  return (
    <div className="workspace-topbar__actions" ref={rootRef}>
      <div className="workspace-topbar__tool-rail" {...tourAnchor("shell.topbar.actions")}>
        <TopbarActionTrigger
          label={t("common.docs")}
          asset="/topbar-assets/docs.svg"
          active={openPanel === "docs"}
          anchor="shell.topbar.actions.docs"
          onClick={() => setOpenPanel((current) => (current === "docs" ? null : "docs"))}
        />
        <TopbarActionTrigger
          label={t("common.ask")}
          asset="/topbar-assets/ask.svg"
          active={openPanel === "ask"}
          anchor="shell.topbar.actions.ask"
          onClick={() => setOpenPanel((current) => (current === "ask" ? null : "ask"))}
        />
        <TopbarActionTrigger
          label={t("common.files")}
          asset="/topbar-assets/files.svg"
          active={openPanel === "files"}
          iconOnly
          anchor="shell.topbar.actions.files"
          onClick={() => setOpenPanel((current) => (current === "files" ? null : "files"))}
        />
        <TopbarActionTrigger
          label={t("common.notifications")}
          asset="/topbar-assets/notifications.svg"
          active={openPanel === "notifications"}
          iconOnly
          highlight
          anchor="shell.topbar.actions.notifications"
          onClick={() => setOpenPanel((current) => (current === "notifications" ? null : "notifications"))}
        />

        {typeof document !== "undefined"
          ? createPortal(
              <AnimatePresence initial={false}>
                {openPanel ? (
                  <motion.div
                    key={openPanel}
                    ref={panelRef}
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
                    className={cn("workspace-topbar__panel", activePanelWidthClass)}
                    role="dialog"
                    aria-label={openPanel ?? undefined}
                    {...tourAnchor(`shell.topbar.actions.panel.${openPanel}`)}
                    style={{
                      position: "fixed",
                      top: panelPosition?.top ?? 0,
                      left: panelPosition?.left ?? 0,
                      width: panelPosition?.width,
                      maxHeight: panelPosition?.maxHeight,
                      background:
                        "linear-gradient(180deg, rgba(24, 24, 28, 0.16), rgba(10, 10, 12, 0.24)), rgba(8, 8, 10, 0.08)",
                      backdropFilter: "blur(52px) saturate(168%) brightness(1.08)",
                      WebkitBackdropFilter:
                        "blur(52px) saturate(168%) brightness(1.08)",
                      visibility: panelPosition ? "visible" : "hidden",
                    }}
                  >
              {openPanel === "docs" ? (
                <div className="workspace-topbar__panel-inner">
                  <div className="workspace-topbar__panel-header">
                    <div>
                      <p className="eyebrow">{t("topbar.docs.eyebrow")}</p>
                      <h3 className="workspace-topbar__panel-title">{t("topbar.docs.title")}</h3>
                    </div>
                    <p className="workspace-topbar__panel-copy">
                      {t("topbar.docs.description")}
                    </p>
                  </div>

                  <div className="workspace-topbar__panel-stack">
                    <button
                      type="button"
                      className="workspace-topbar__shortcut-card text-left"
                      onClick={handleTourShortcut}
                      {...tourAnchor("shell.topbar.actions.restart-tour")}
                    >
                      <div className="min-w-0">
                        <p className="eyebrow text-[10px] text-[var(--text-quaternary)]">
                          {t("tour.topbar.eyebrow")}
                        </p>
                        <p className="workspace-topbar__shortcut-title">
                          {status === "running"
                            ? t("tour.topbar.resumeTitle")
                            : t("tour.topbar.title")}
                        </p>
                        <p className="workspace-topbar__shortcut-copy">
                          {status === "running"
                            ? t("tour.topbar.resumeDescription")
                            : t("tour.topbar.description")}
                        </p>
                      </div>
                      <ArrowUpRight className="h-4 w-4 shrink-0 text-[var(--text-quaternary)]" />
                    </button>
                    {docEntries.map((entry) => (
                      <Link
                        key={entry.title}
                        href={entry.href}
                        className="workspace-topbar__shortcut-card"
                        onClick={() => setOpenPanel(null)}
                      >
                        <div className="min-w-0">
                          <p className="eyebrow text-[10px] text-[var(--text-quaternary)]">{entry.eyebrow}</p>
                          <p className="workspace-topbar__shortcut-title">{entry.title}</p>
                          <p className="workspace-topbar__shortcut-copy">{entry.description}</p>
                        </div>
                        <ArrowUpRight className="h-4 w-4 shrink-0 text-[var(--text-quaternary)]" />
                      </Link>
                    ))}
                  </div>
                </div>
              ) : null}

              {openPanel === "ask" ? (
                <div className="workspace-topbar__panel-inner">
                  <div className="workspace-topbar__panel-header">
                    <div>
                      <p className="eyebrow">{t("topbar.ask.eyebrow")}</p>
                      <h3 className="workspace-topbar__panel-title">{t("topbar.ask.title")}</h3>
                    </div>
                    <p className="workspace-topbar__panel-copy">
                      {t("topbar.ask.description")}
                    </p>
                  </div>

                  <label className="workspace-topbar__ask-field">
                    <Search className="mt-0.5 h-4 w-4 shrink-0 text-[var(--text-quaternary)]" />
                    <textarea
                      value={askPrompt}
                      onChange={(event) => setAskPrompt(event.target.value)}
                      rows={3}
                      className="workspace-topbar__ask-input"
                      placeholder={t("topbar.ask.placeholder")}
                    />
                  </label>

                  <div className="workspace-topbar__ask-suggestions">
                    {askSuggestions.map((suggestion) => (
                      <button
                        key={suggestion}
                        type="button"
                        className="workspace-topbar__suggestion"
                        onClick={() => handleAskSubmit(suggestion)}
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>

                  <div className="workspace-topbar__ask-response">
                    <div className="flex items-center justify-between gap-3">
                      <span className="eyebrow text-[10px] text-[var(--text-quaternary)]">
                        {t("topbar.ask.responseLabel")}
                      </span>
                      <button
                        type="button"
                        className="button-shell button-shell--primary button-shell--sm"
                        onClick={() => handleAskSubmit()}
                        disabled={askLoading || askPrompt.trim().length === 0}
                      >
                        {askLoading ? t("topbar.ask.loadingButton") : t("topbar.ask.button")}
                      </button>
                    </div>
                    <p className={cn("workspace-topbar__ask-copy", askLoading && "workspace-topbar__ask-copy--loading")}>
                      {askLoading ? t("topbar.ask.loadingCopy") : askReply}
                    </p>
                  </div>
                </div>
              ) : null}

              {openPanel === "files" ? (
                <div className="workspace-topbar__panel-inner">
                  <div className="workspace-topbar__panel-header">
                    <div>
                      <p className="eyebrow">{t("topbar.files.eyebrow")}</p>
                      <h3 className="workspace-topbar__panel-title">{t("topbar.files.title")}</h3>
                    </div>
                    <p className="workspace-topbar__panel-copy">
                      {t("topbar.files.description")}
                    </p>
                  </div>

                  <div className="workspace-topbar__panel-stack">
                    {fileEntries.map((entry) => (
                      <Link
                        key={entry.name}
                        href={entry.href}
                        className="workspace-topbar__file-card"
                        onClick={() => setOpenPanel(null)}
                      >
                        <div className="workspace-topbar__file-icon">
                          <FileText className="h-4 w-4" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="workspace-topbar__file-name">{entry.name}</p>
                          <p className="workspace-topbar__file-detail">{entry.detail}</p>
                        </div>
                        <div className="workspace-topbar__file-meta">
                          <span>{entry.updatedAt}</span>
                          <ChevronRight className="h-4 w-4" />
                        </div>
                      </Link>
                    ))}
                  </div>
                </div>
              ) : null}

              {openPanel === "notifications" ? (
                <div className="workspace-topbar__panel-inner workspace-topbar__panel-inner--notifications">
                  <div className="workspace-topbar__panel-header">
                    <div>
                      <p className="eyebrow">{t("topbar.notifications.eyebrow")}</p>
                      <h3 className="workspace-topbar__panel-title">{t("topbar.notifications.title")}</h3>
                    </div>
                    <p className="workspace-topbar__panel-copy">
                      {t("topbar.notifications.description")}
                    </p>
                  </div>

                  <div className="workspace-topbar__notifications-summary">
                    <span>{t("topbar.notifications.summaryLeft", { count: notificationEntries.length })}</span>
                    <span>{t("topbar.notifications.summaryRight")}</span>
                  </div>

                  <div className="workspace-topbar__panel-stack">
                    {notificationEntries.map((entry) => (
                      <Link
                        key={entry.title}
                        href={entry.href}
                        className="workspace-topbar__notice-card"
                        onClick={() => setOpenPanel(null)}
                      >
                        <div className="workspace-topbar__notice-meta">
                          <span className="workspace-topbar__notice-section">{entry.section}</span>
                          <span className="workspace-topbar__notice-time">{entry.timestamp}</span>
                        </div>
                        <div className="min-w-0">
                          <h4 className="workspace-topbar__notice-title">{entry.title}</h4>
                          <p className="workspace-topbar__notice-copy">{entry.description}</p>
                        </div>
                      </Link>
                    ))}
                  </div>
                </div>
              ) : null}
                  </motion.div>
                ) : null}
              </AnimatePresence>,
              document.body,
            )
          : null}
      </div>
    </div>
  );
}
