"use client";

import { useCallback, useMemo, type ReactNode } from "react";
import {
  Download,
  ExternalLink,
  File,
  FileCode2,
  FileJson,
  FileSpreadsheet,
  FileText,
  ImageIcon,
  Link2,
  PanelRight,
  PlayCircle,
  Settings2,
  Users,
  Volume2,
} from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";
import type { RoomEntry } from "@/hooks/use-rooms";
import type { SquadThreadOverviewResponse } from "@/lib/squads";
import type {
  ExecutionArtifact,
  SessionDetail,
  SessionSummary,
} from "@/lib/types";

interface SessionArtifactRailProps {
  detail: SessionDetail | null;
  summary: SessionSummary | null;
  room?: RoomEntry | null;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  onOpenRoomSettings?: () => void;
  onOpenArtifact?: (artifact: ExecutionArtifact) => void;
  roomThreadMessages?: SquadThreadOverviewResponse["recentMessages"];
  className?: string;
}

function readArtifactFilename(artifact: ExecutionArtifact) {
  const candidate = artifact.path || artifact.url || artifact.label;
  if (!candidate) return null;
  try {
    const parsed = candidate.startsWith("http") ? new URL(candidate) : null;
    const pathname = parsed ? parsed.pathname : candidate;
    const fileName = pathname.split("/").filter(Boolean).pop();
    return fileName || candidate;
  } catch {
    const fileName = candidate.split("/").filter(Boolean).pop();
    return fileName || candidate;
  }
}

function ArtifactKindGlyph({ kind }: { kind: ExecutionArtifact["kind"] }) {
  const className = "h-3.5 w-3.5 text-[var(--text-tertiary)]";
  switch (kind) {
    case "image":
      return <ImageIcon className={className} strokeWidth={1.75} />;
    case "video":
      return <PlayCircle className={className} strokeWidth={1.75} />;
    case "audio":
      return <Volume2 className={className} strokeWidth={1.75} />;
    case "spreadsheet":
    case "csv":
    case "tsv":
      return <FileSpreadsheet className={className} strokeWidth={1.75} />;
    case "json":
    case "yaml":
    case "xml":
    case "html":
      return <FileJson className={className} strokeWidth={1.75} />;
    case "code":
      return <FileCode2 className={className} strokeWidth={1.75} />;
    case "url":
      return <Link2 className={className} strokeWidth={1.75} />;
    case "pdf":
    case "docx":
    case "text":
      return <FileText className={className} strokeWidth={1.75} />;
    default:
      return <File className={className} strokeWidth={1.75} />;
  }
}

export function collectArtifactsFromDetail(
  detail: SessionDetail | null,
): ExecutionArtifact[] {
  if (!detail) return [];
  const seen = new Set<string>();
  const items: ExecutionArtifact[] = [];
  // Walk messages newest-first so the rail surfaces the most recent artefacts
  // at the top, matching the Claude.ai reference.
  for (let index = detail.messages.length - 1; index >= 0; index -= 1) {
    const message = detail.messages[index];
    if (!message.artifacts || message.artifacts.length === 0) continue;
    for (const artifact of message.artifacts) {
      // Skip empty/text-only assistant responses with no payload — they would
      // produce noise rows ("Untitled") in the rail.
      if (
        artifact.kind === "text" &&
        artifact.source_type === "assistant_response" &&
        !artifact.url &&
        !artifact.path
      ) {
        continue;
      }
      const key =
        artifact.id ||
        artifact.url ||
        artifact.path ||
        `${message.id}:${items.length}`;
      if (seen.has(key)) continue;
      seen.add(key);
      items.push(artifact);
    }
  }
  return items;
}

export function SessionArtifactRail({
  detail,
  summary,
  room = null,
  open = true,
  onOpenChange,
  onOpenRoomSettings,
  onOpenArtifact,
  roomThreadMessages = [],
  className,
}: SessionArtifactRailProps) {
  const { t } = useAppI18n();
  const items = useMemo(() => collectArtifactsFromDetail(detail), [detail]);

  const handleClick = useCallback(
    (artifact: ExecutionArtifact) => {
      onOpenArtifact?.(artifact);
    },
    [onOpenArtifact],
  );

  if (!summary && !room) return null;
  if (!room && items.length === 0) return null;
  if (!open) return null;

  return (
    <aside
      className={cn(
        "hidden w-[320px] shrink-0 flex-col overflow-hidden border-l border-[color:var(--divider-hair)] bg-[var(--canvas)] lg:flex",
        className,
      )}
      aria-label={t("sessions.context.title", { defaultValue: "Session details" })}
    >
      <div className="flex justify-end px-3 pt-3">
        <button
          type="button"
          onClick={() => onOpenChange?.(false)}
          aria-label={t("sessions.context.collapse", { defaultValue: "Collapse panel" })}
          aria-expanded={open}
          className={cn(
            "inline-flex h-7 w-7 items-center justify-center rounded-[var(--radius-panel-sm)]",
            "text-[var(--text-tertiary)] transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
            "hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]",
          )}
        >
          <PanelRight className="h-4 w-4" strokeWidth={1.75} aria-hidden />
        </button>
      </div>

      <div className="flex flex-col gap-3 px-4 pt-2 pb-5">
        {room ? (
          <RoomContextCard
            room={room}
            onOpenRoomSettings={onOpenRoomSettings}
          />
        ) : null}
        {room ? <ThreadReplyCard messages={roomThreadMessages} /> : null}
        {summary && items.length > 0 ? (
          <SuspendedCard
            title={t("sessions.context.artifacts.downloadsTitle", {
              defaultValue: "Files",
            })}
            trailing={
              <span className="font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                {items.length}
              </span>
            }
          >
            <ul className="flex max-h-[260px] flex-col overflow-y-auto overscroll-contain">
              {items.map((artifact, index) => (
                <ArtifactRow
                  key={`${artifact.id}-${index}`}
                  artifact={artifact}
                  onClick={onOpenArtifact ? () => handleClick(artifact) : undefined}
                />
              ))}
            </ul>
          </SuspendedCard>
        ) : null}
      </div>
    </aside>
  );
}

function ThreadReplyCard({
  messages,
}: {
  messages: SquadThreadOverviewResponse["recentMessages"];
}) {
  const { t } = useAppI18n();
  const replyMessages = messages.filter(
    (message) =>
      message.inReplyTo ||
      message.type === "coordinator_synthesis" ||
      Number(message.replySummary?.open ?? 0) > 0 ||
      Number(message.replySummary?.answered ?? 0) > 0,
  );
  const openObligations = messages.flatMap((message) =>
    (message.replyObligations ?? []).filter((obligation) => obligation.status === "open"),
  );
  if (replyMessages.length === 0 && openObligations.length === 0) return null;

  return (
    <SuspendedCard
      title={t("sessions.context.thread.title", { defaultValue: "Thread" })}
      trailing={
        openObligations.length > 0 ? (
          <span className="font-mono text-[0.6875rem] text-[var(--tone-warning-text)]">
            {openObligations.length}
          </span>
        ) : null
      }
    >
      <div className="flex max-h-[260px] flex-col gap-1 overflow-y-auto px-2 pb-2">
        {openObligations.length > 0 ? (
          <div className="rounded-[var(--radius-panel-sm)] bg-[var(--tone-warning-bg)] px-2 py-1.5">
            <p className="m-0 font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--tone-warning-text)]">
              {t("sessions.context.thread.waiting", {
                defaultValue: "Waiting",
              })}
            </p>
            {openObligations.slice(0, 4).map((obligation) => (
              <p
                key={obligation.id}
                className="m-0 mt-1 truncate text-[0.75rem] text-[var(--text-secondary)]"
              >
                {obligation.targetAgentId}
              </p>
            ))}
          </div>
        ) : null}
        {replyMessages.slice(0, 6).map((message) => (
          <div
            key={message.id}
            className="rounded-[var(--radius-panel-sm)] px-2 py-1.5 text-[0.75rem] hover:bg-[var(--hover-tint)]"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-medium text-[var(--text-primary)]">
                {message.from ?? "system"}
              </span>
              <span className="font-mono text-[0.625rem] text-[var(--text-quaternary)]">
                {message.type === "coordinator_synthesis"
                  ? t("sessions.context.thread.final", { defaultValue: "Final" })
                  : message.inReplyTo ?? `#${message.id}`}
              </span>
            </div>
            <p className="m-0 mt-0.5 line-clamp-2 text-[var(--text-tertiary)]">
              {message.content}
            </p>
          </div>
        ))}
      </div>
    </SuspendedCard>
  );
}

function SuspendedCard({
  title,
  trailing,
  children,
}: {
  title: string;
  trailing?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-[var(--radius-panel)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] shadow-[var(--shadow-xs)]">
      <header className="flex items-center justify-between gap-2 px-3.5 pt-3 pb-2">
        <h3 className="m-0 text-[var(--font-size-sm)] font-medium text-[var(--text-primary)]">
          {title}
        </h3>
        {trailing}
      </header>
      <div className="px-1.5 pb-2">{children}</div>
    </section>
  );
}

function RoomContextCard({
  room,
  onOpenRoomSettings,
}: {
  room: RoomEntry;
  onOpenRoomSettings?: () => void;
}) {
  const { t } = useAppI18n();
  const coordinator = room.thread.coordinatorAgentId ?? room.squad.coordinatorAgentId;
  const memberLabel =
    room.squad.memberCount === 1
      ? t("sessions.context.room.memberSingular", {
          defaultValue: "{{count}} agent",
          count: room.squad.memberCount,
        })
      : t("sessions.context.room.memberPlural", {
          defaultValue: "{{count}} agents",
          count: room.squad.memberCount,
        });

  return (
    <SuspendedCard
      title={t("sessions.context.room.title", { defaultValue: "Room" })}
      trailing={
        onOpenRoomSettings ? (
          <button
            type="button"
            onClick={onOpenRoomSettings}
            className="inline-flex h-7 w-7 items-center justify-center rounded-[var(--radius-panel-sm)] text-[var(--text-tertiary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--panel-soft)]"
            aria-label={t("sessions.room.settings.open", {
              defaultValue: "Room settings",
            })}
          >
            <Settings2 className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          </button>
        ) : null
      }
    >
      <div className="flex flex-col gap-2 px-2 pb-2">
        <div className="flex items-center gap-2 rounded-[var(--radius-panel-sm)] px-1 py-1">
          {room.thread.photoUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={room.thread.photoUrl}
              alt=""
              aria-hidden
              referrerPolicy="no-referrer"
              className="h-7 w-7 shrink-0 rounded-full object-cover"
            />
          ) : (
            <span
              aria-hidden
              className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--panel-strong)] text-[var(--text-tertiary)]"
            >
              <Users className="h-3.5 w-3.5" strokeWidth={1.75} />
            </span>
          )}
          <span className="flex min-w-0 flex-col">
            <span className="truncate text-[0.8125rem] font-medium text-[var(--text-primary)]">
              {room.thread.title || room.squad.squadId}
            </span>
            <span className="truncate font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
              {room.thread.status}
            </span>
          </span>
        </div>
        <dl className="grid grid-cols-1 gap-2 px-1">
          <div className="flex items-center justify-between gap-3">
            <dt className="font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
              {t("sessions.context.room.participants", {
                defaultValue: "Participants",
              })}
            </dt>
            <dd className="m-0 truncate text-[0.75rem] text-[var(--text-secondary)]">
              {memberLabel}
            </dd>
          </div>
          <div className="flex items-center justify-between gap-3">
            <dt className="font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
              {t("sessions.context.room.coordinator", {
                defaultValue: "Coordinator",
              })}
            </dt>
            <dd className="m-0 truncate font-mono text-[0.75rem] text-[var(--text-secondary)]">
              {coordinator ?? "—"}
            </dd>
          </div>
        </dl>
      </div>
    </SuspendedCard>
  );
}

function ArtifactRow({
  artifact,
  onClick,
}: {
  artifact: ExecutionArtifact;
  onClick?: () => void;
}) {
  const { t } = useAppI18n();
  const fileName =
    readArtifactFilename(artifact) ||
    artifact.label ||
    t("sessions.context.artifacts.unknown", { defaultValue: "Untitled" });
  const isExternal = Boolean(
    artifact.kind === "url" || (artifact.url && /^https?:\/\//i.test(artifact.url)),
  );

  const content = (
    <>
      <span
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[var(--radius-panel-sm)] bg-[var(--panel-strong)]"
        aria-hidden
      >
        <ArtifactKindGlyph kind={artifact.kind} />
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-[0.8125rem] font-medium text-[var(--text-primary)]">
          {fileName}
        </span>
        {artifact.label && artifact.label !== fileName ? (
          <span className="truncate text-[0.6875rem] text-[var(--text-quaternary)]">
            {artifact.label}
          </span>
        ) : null}
      </span>
      <span
        className="shrink-0 text-[var(--text-quaternary)] opacity-0 transition-opacity group-hover:opacity-100"
        aria-hidden
      >
        {isExternal ? (
          <ExternalLink className="h-3.5 w-3.5" strokeWidth={1.75} />
        ) : (
          <Download className="h-3.5 w-3.5" strokeWidth={1.75} />
        )}
      </span>
    </>
  );

  return (
    <li className="contents">
      {onClick ? (
        <button
          type="button"
          onClick={onClick}
          className={cn(
            "group flex w-full items-center gap-2 rounded-[var(--radius-panel-sm)] px-2 py-1.5 text-left",
            "transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
            "hover:bg-[var(--hover-tint)]",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--panel-soft)]",
          )}
        >
          {content}
        </button>
      ) : (
        <div className="group flex w-full items-center gap-2 rounded-[var(--radius-panel-sm)] px-2 py-1.5">
          {content}
        </div>
      )}
    </li>
  );
}
