"use client";

import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";
import {
  ExternalLink,
  File,
  FileCode2,
  FileJson,
  FileSpreadsheet,
  FileText,
  Globe,
  ImageIcon,
  Info,
  Link2,
  MessageSquareText,
  PlayCircle,
  Volume2,
} from "lucide-react";
import { StatusIndicator } from "@/components/dashboard/status-indicator";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  fetchControlPlaneDashboardJson,
  fetchControlPlaneDashboardJsonAllowError,
} from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";
import type {
  ExecutionArtifact,
  ExecutionArtifactLinkPreview,
  ExecutionDetail,
  ExecutionSummary,
  SessionDetail,
  SessionSummary,
} from "@/lib/types";
import { formatCost, formatRelativeTime, truncateText } from "@/lib/utils";

const ARTIFACT_EXECUTION_LIMIT = 12;
const ARTIFACT_LINK_PREVIEW_LIMIT = 8;

type SessionSummaryLike = SessionSummary & {
  agent_id?: string | null;
};

type ExecutionSummaryLike = ExecutionSummary & {
  agent_id?: string | null;
};

type SessionArtifactItem = ExecutionArtifact & {
  execution: ExecutionSummaryLike;
  activityAt: string | null;
  dedupeKey: string;
};

function dedupeExecutions(detail: SessionDetail | null) {
  if (!detail) return [];
  const byId = new Map<number, ExecutionSummaryLike>();
  for (const execution of detail.orphan_executions) {
    byId.set(execution.task_id, execution);
  }
  for (const message of detail.messages) {
    if (message.linked_execution) {
      byId.set(message.linked_execution.task_id, message.linked_execution);
    }
  }
  return [...byId.values()].sort((left, right) => {
    const leftTime = new Date(left.completed_at || left.started_at || left.created_at).getTime();
    const rightTime = new Date(right.completed_at || right.started_at || right.created_at).getTime();
    return rightTime - leftTime;
  });
}

function resolveSummaryBotId(summary: SessionSummary | null | undefined) {
  if (!summary) return null;
  const withAgent = summary as SessionSummaryLike;
  return withAgent.bot_id || withAgent.agent_id || null;
}

function resolveExecutionBotId(execution: ExecutionSummaryLike | null | undefined) {
  if (!execution) return null;
  return execution.bot_id || execution.agent_id || null;
}

function isHttpUrl(value: string | null | undefined) {
  return Boolean(value && /^https?:\/\//i.test(value));
}

function formatFileSize(sizeBytes: number | null | undefined) {
  if (typeof sizeBytes !== "number" || !Number.isFinite(sizeBytes) || sizeBytes <= 0) {
    return null;
  }
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} KB`;
  if (sizeBytes < 1024 * 1024 * 1024) return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(sizeBytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
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

function artifactKindLabel(kind: ExecutionArtifact["kind"], t: ReturnType<typeof useAppI18n>["t"]) {
  const fallback = {
    image: "Image",
    audio: "Audio",
    video: "Video",
    pdf: "PDF",
    docx: "Document",
    spreadsheet: "Spreadsheet",
    text: "Text",
    html: "HTML",
    json: "JSON",
    yaml: "YAML",
    xml: "XML",
    csv: "CSV",
    tsv: "TSV",
    url: "Link",
    code: "Code",
    file: "File",
  }[kind];
  return t(`sessions.context.artifacts.kind.${kind}`, { defaultValue: fallback });
}

function artifactGroupLabel(kind: ExecutionArtifact["kind"]) {
  if (kind === "url") return "Links";
  if (kind === "image" || kind === "video" || kind === "audio") return "Media";
  if (kind === "pdf" || kind === "docx" || kind === "spreadsheet" || kind === "file") return "Files";
  return "Content";
}

function ArtifactKindGlyph({ kind }: { kind: ExecutionArtifact["kind"] }) {
  switch (kind) {
    case "image":
      return <ImageIcon className="h-4.5 w-4.5" />;
    case "video":
      return <PlayCircle className="h-4.5 w-4.5" />;
    case "audio":
      return <Volume2 className="h-4.5 w-4.5" />;
    case "spreadsheet":
    case "csv":
    case "tsv":
      return <FileSpreadsheet className="h-4.5 w-4.5" />;
    case "json":
    case "yaml":
    case "xml":
    case "html":
      return <FileJson className="h-4.5 w-4.5" />;
    case "code":
      return <FileCode2 className="h-4.5 w-4.5" />;
    case "url":
      return <Link2 className="h-4.5 w-4.5" />;
    case "pdf":
    case "docx":
    case "text":
      return <FileText className="h-4.5 w-4.5" />;
    default:
      return <File className="h-4.5 w-4.5" />;
  }
}

function buildArtifactItems(executionDetails: Array<{ execution: ExecutionSummaryLike; detail: ExecutionDetail }>) {
  const items: SessionArtifactItem[] = [];
  const seen = new Set<string>();
  const sorted = [...executionDetails].sort((left, right) => {
    const leftTime = new Date(
      left.execution.completed_at || left.execution.started_at || left.execution.created_at
    ).getTime();
    const rightTime = new Date(
      right.execution.completed_at || right.execution.started_at || right.execution.created_at
    ).getTime();
    return rightTime - leftTime;
  });

  for (const item of sorted) {
    for (const artifact of item.detail.artifacts) {
      if (artifact.kind === "text" && artifact.source_type === "assistant_response" && !artifact.url) {
        continue;
      }
      const dedupeKey = artifact.url || artifact.path || `${item.detail.task_id}:${artifact.id}`;
      if (seen.has(dedupeKey)) continue;
      seen.add(dedupeKey);
      items.push({
        ...artifact,
        execution: item.execution,
        activityAt: item.execution.completed_at || item.execution.started_at || item.execution.created_at,
        dedupeKey,
      });
    }
  }

  return items;
}

function MetaBlock({
  label,
  value,
}: {
  label: string;
  value: string | number | null | undefined;
}) {
  return (
    <div className="rounded-[1.05rem] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-3.5 py-3">
      <p className="text-[10px] uppercase tracking-[0.16em] text-[var(--text-quaternary)]">{label}</p>
      <p className="mt-2 text-[15px] font-semibold tracking-[-0.02em] text-[var(--text-primary)]">
        {value ?? "—"}
      </p>
    </div>
  );
}

function ArtifactMetric({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-[1.05rem] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-3.5 py-3">
      <p className="text-[10px] uppercase tracking-[0.16em] text-[var(--text-quaternary)]">{label}</p>
      <p className="mt-2 text-[15px] font-semibold tracking-[-0.02em] text-[var(--text-primary)]">{value}</p>
    </div>
  );
}

function ArtifactSkeleton() {
  return (
    <div className="rounded-[1.2rem] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] p-4">
      <div className="skeleton h-4 w-20 rounded-full" />
      <div className="mt-3 skeleton h-6 w-4/5 rounded-full" />
      <div className="mt-3 skeleton h-20 w-full rounded-[1rem]" />
      <div className="mt-3 skeleton h-4 w-2/3 rounded-full" />
    </div>
  );
}

function ArtifactEmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-[1.25rem] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-5 py-6 text-center">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-[1.15rem] border border-[var(--border-subtle)] bg-[var(--surface-hover)] text-[var(--text-tertiary)]">
        <Globe className="h-5 w-5" />
      </div>
      <p className="mt-4 text-sm font-semibold text-[var(--text-primary)]">{title}</p>
      <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{description}</p>
    </div>
  );
}

function ArtifactCard({
  artifact,
  preview,
  t,
}: {
  artifact: SessionArtifactItem;
  preview: ExecutionArtifactLinkPreview | null;
  t: ReturnType<typeof useAppI18n>["t"];
}) {
  const externalUrl =
    (preview?.final_url && isHttpUrl(preview.final_url) ? preview.final_url : null) ||
    (artifact.url && isHttpUrl(artifact.url) ? artifact.url : null);
  const previewImage =
    (preview?.image_url && isHttpUrl(preview.image_url) ? preview.image_url : null) ||
    (artifact.preview_image_url && isHttpUrl(artifact.preview_image_url) ? artifact.preview_image_url : null);
  const title =
    preview?.title ||
    artifact.label ||
    readArtifactFilename(artifact) ||
    artifactKindLabel(artifact.kind, t);
  const description =
    preview?.description ||
    artifact.summary ||
    artifact.description ||
    artifact.text_content ||
    (typeof artifact.content === "string" ? artifact.content : null);
  const fileName = readArtifactFilename(artifact);
  const fileSize = formatFileSize(artifact.size_bytes);
  const domain = preview?.domain || artifact.domain;
  const siteName = preview?.site_name || artifact.site_name;
  const kindLabel = artifactKindLabel(artifact.kind, t);
  const executionTitle = truncateText(
    artifact.execution.query_text || t("sessions.context.artifacts.executionFallback", { defaultValue: "Execution" }),
    46,
  );

  return (
    <article className="overflow-hidden rounded-[1.2rem] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)]">
      {previewImage ? (
        <div className="relative h-32 w-full overflow-hidden border-b border-[var(--border-subtle)] bg-[var(--surface-hover)]">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={previewImage}
            alt={title}
            className="h-full w-full object-cover"
            loading="lazy"
            referrerPolicy="no-referrer"
          />
        </div>
      ) : (
        <div className="flex items-center gap-3 border-b border-[var(--border-subtle)] bg-[var(--surface-hover)] px-4 py-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[0.95rem] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] text-[var(--text-primary)]">
            <ArtifactKindGlyph kind={artifact.kind} />
          </div>
          <div className="min-w-0">
            <p className="truncate text-[12px] font-medium text-[var(--text-primary)]">{title}</p>
            <p className="truncate text-[11px] text-[var(--text-tertiary)]">
              {siteName || domain || fileName || kindLabel}
            </p>
          </div>
        </div>
      )}

      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-hover)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
                {kindLabel}
              </span>
              {artifact.unavailable ? (
                <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-hover)] px-2.5 py-1 text-[10px] font-medium text-[var(--text-tertiary)]">
                  {t("sessions.context.artifacts.unavailable", { defaultValue: "Unavailable" })}
                </span>
              ) : null}
            </div>
            <h4 className="mt-3 text-[15px] font-semibold leading-6 tracking-[-0.02em] text-[var(--text-primary)]">
              {title}
            </h4>
          </div>

          {externalUrl ? (
            <a
              href={externalUrl}
              target="_blank"
              rel="noreferrer"
              className="button-shell button-shell--secondary button-shell--icon h-9 w-9 shrink-0 text-[var(--text-secondary)]"
              aria-label={t("sessions.context.artifacts.openExternal", {
                defaultValue: "Open in a new tab",
              })}
            >
              <ExternalLink className="h-4 w-4" />
            </a>
          ) : null}
        </div>

        {description ? (
          <p className="mt-3 line-clamp-3 text-[13px] leading-6 text-[var(--text-secondary)]">
            {description}
          </p>
        ) : null}

        <div className="mt-4 flex flex-wrap gap-2">
          {siteName && !previewImage ? (
            <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-hover)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">
              {siteName}
            </span>
          ) : null}
          {domain ? (
            <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-hover)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">
              {domain}
            </span>
          ) : null}
          {fileName && fileName !== title ? (
            <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-hover)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">
              {truncateText(fileName, 28)}
            </span>
          ) : null}
          {fileSize ? (
            <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-hover)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">
              {fileSize}
            </span>
          ) : null}
          {preview?.duration ? (
            <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-hover)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">
              {preview.duration}
            </span>
          ) : null}
        </div>

        <div className="mt-4 border-t border-[var(--border-subtle)] pt-3 text-[11px] text-[var(--text-tertiary)]">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>{formatRelativeTime(artifact.activityAt)}</span>
            <span>•</span>
            <span>#{artifact.execution.task_id}</span>
            <span>•</span>
            <span className="truncate">{executionTitle}</span>
          </div>
        </div>
      </div>
    </article>
  );
}

interface SessionContextPanelProps {
  detail: SessionDetail | null;
  summary: SessionSummary | null;
  className?: string;
}

export function SessionContextPanel({
  detail,
  summary,
  className,
}: SessionContextPanelProps) {
  const { t } = useAppI18n();
  const fallbackExecutions = useMemo(() => dedupeExecutions(detail), [detail]);
  const sessionBotId = resolveSummaryBotId(summary) || resolveSummaryBotId(detail?.summary ?? null);
  const sessionId = summary?.session_id || detail?.summary.session_id || null;

  const executionsQuery = useControlPlaneQuery<{
    items: ExecutionSummaryLike[];
  }>({
    tier: "live",
    queryKey: queryKeys.dashboard.executions({
      botIds: sessionBotId ? [sessionBotId] : [],
      sessionId: sessionId ?? undefined,
      limit: ARTIFACT_EXECUTION_LIMIT,
    }),
    enabled: Boolean(sessionBotId && sessionId),
    refetchInterval: 15_000,
    queryFn: async ({ signal }) => {
      if (!sessionBotId || !sessionId) {
        return { items: fallbackExecutions.slice(0, ARTIFACT_EXECUTION_LIMIT) };
      }

      const response = await fetchControlPlaneDashboardJsonAllowError<ExecutionSummaryLike[]>(
        `/agents/${sessionBotId}/executions`,
        {
          signal,
          params: {
            sessionId,
            limit: ARTIFACT_EXECUTION_LIMIT,
          },
          fallbackError: t("sessions.loadError"),
        },
      );

      return {
        items: Array.isArray(response.data) && response.data.length > 0
          ? response.data
          : fallbackExecutions.slice(0, ARTIFACT_EXECUTION_LIMIT),
      };
    },
  });

  const executions = useMemo(() => {
    if (executionsQuery.data?.items?.length) {
      return executionsQuery.data.items;
    }
    return fallbackExecutions.slice(0, ARTIFACT_EXECUTION_LIMIT);
  }, [executionsQuery.data?.items, fallbackExecutions]);

  const executionDetailsQueries = useQueries({
    queries: executions.map((execution) => {
      const executionBotId = resolveExecutionBotId(execution);
      return {
        queryKey: queryKeys.dashboard.executionDetail(executionBotId ?? "", execution.task_id),
        enabled: Boolean(executionBotId),
        staleTime: 30_000,
        queryFn: async ({ signal }: { signal: AbortSignal }) => {
          if (!executionBotId) {
            throw new Error(t("sessions.loadError"));
          }
          return fetchControlPlaneDashboardJson<ExecutionDetail>(
            `/agents/${executionBotId}/executions/${execution.task_id}`,
            {
              signal,
              fallbackError: t("sessions.loadError"),
            },
          );
        },
      };
    }),
  });

  const executionDetails = useMemo(
    () =>
      executionDetailsQueries.flatMap((result, index) =>
        result.data ? [{ execution: executions[index], detail: result.data }] : []
      ),
    [executionDetailsQueries, executions]
  );

  const artifactItems = useMemo(() => buildArtifactItems(executionDetails), [executionDetails]);
  const linkArtifacts = useMemo(
    () =>
      artifactItems
        .filter((artifact) => artifact.kind === "url" && artifact.url)
        .slice(0, ARTIFACT_LINK_PREVIEW_LIMIT),
    [artifactItems]
  );

  const linkPreviewQueries = useQueries({
    queries: linkArtifacts.map((artifact) => ({
      queryKey: ["dashboard", "link-preview", artifact.url] as const,
      enabled: Boolean(artifact.url),
      staleTime: 10 * 60_000,
      queryFn: async ({ signal }: { signal: AbortSignal }) => {
        const response = await fetchControlPlaneDashboardJsonAllowError<ExecutionArtifactLinkPreview>(
          "/link-preview",
          {
            signal,
            params: { url: artifact.url },
            fallbackError: t("sessions.context.artifacts.previewUnavailable", {
              defaultValue: "Link preview is unavailable.",
            }),
          }
        );
        return response.data;
      },
    })),
  });

  const linkPreviewByUrl = useMemo(() => {
    const previews = new Map<string, ExecutionArtifactLinkPreview | null>();
    linkArtifacts.forEach((artifact, index) => {
      if (!artifact.url) return;
      previews.set(artifact.url, linkPreviewQueries[index]?.data ?? null);
    });
    return previews;
  }, [linkArtifacts, linkPreviewQueries]);

  const groupedArtifacts = useMemo(() => {
    const groups = new Map<string, SessionArtifactItem[]>();
    for (const artifact of artifactItems) {
      const key = artifactGroupLabel(artifact.kind);
      const current = groups.get(key) ?? [];
      current.push(artifact);
      groups.set(key, current);
    }
    return [...groups.entries()];
  }, [artifactItems]);

  const artifactCount = artifactItems.length;
  const linkCount = artifactItems.filter((artifact) => artifact.kind === "url").length;
  const fileCount = artifactItems.filter((artifact) => artifact.kind !== "url").length;
  const isArtifactLoading =
    executionsQuery.isLoading ||
    executionDetailsQueries.some((query) => query.isLoading) ||
    linkPreviewQueries.some((query) => query.isLoading);

  if (!summary || !detail) {
    return (
      <aside
        className={`flex h-full min-h-0 flex-col border-l border-[var(--border-subtle)] bg-[var(--surface-canvas)] ${className ?? ""}`}
      >
        <div className="flex h-full flex-col items-center justify-center px-6 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-[1.35rem] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)]">
            <Info className="h-6 w-6 text-[var(--text-tertiary)]" />
          </div>
          <p className="mt-4 text-lg font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
            {t("sessions.context.emptyTitle", { defaultValue: "Artifacts & conversation details" })}
          </p>
          <p className="mt-2 max-w-xs text-sm leading-6 text-[var(--text-secondary)]">
            {t("sessions.context.emptyDescription", {
              defaultValue:
                "Choose a conversation to inspect generated images, documents, links, execution activity and identifiers.",
            })}
          </p>
        </div>
      </aside>
    );
  }

  const recentExecutions = executions.slice(0, 4);

  return (
    <aside
      className={`flex h-full min-h-0 flex-col border-l border-[var(--border-subtle)] bg-[var(--surface-canvas)] ${className ?? ""}`}
    >
      <div className="border-b border-[var(--border-subtle)] px-5 py-4">
        <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
          {t("sessions.context.artifacts.label", { defaultValue: "Artifacts" })}
        </p>
        <h3 className="mt-2 truncate text-[1rem] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
          {summary.name || summary.latest_message_preview || truncateText(summary.session_id, 28)}
        </h3>
        <div className="mt-2 flex items-center gap-2 text-[12px] text-[var(--text-tertiary)]">
          {summary.latest_status ? <StatusIndicator status={summary.latest_status} /> : null}
          <span>{summary.latest_status || t("sessions.detail.sessionInProgress")}</span>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
        <div className="grid grid-cols-3 gap-3">
          <ArtifactMetric
            label={t("sessions.context.artifacts.total", { defaultValue: "Artifacts" })}
            value={artifactCount}
          />
          <ArtifactMetric
            label={t("sessions.context.artifacts.links", { defaultValue: "Links" })}
            value={linkCount}
          />
          <ArtifactMetric
            label={t("sessions.context.artifacts.files", { defaultValue: "Files" })}
            value={fileCount}
          />
        </div>

        <div className="mt-5">
          <div className="mb-3 flex items-center gap-2">
            <MessageSquareText className="h-4 w-4 text-[var(--text-tertiary)]" />
            <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
              {t("sessions.context.artifacts.sectionTitle", { defaultValue: "Generated artifacts" })}
            </p>
          </div>

          {artifactCount === 0 ? (
            isArtifactLoading ? (
              <div className="space-y-3">
                <ArtifactSkeleton />
                <ArtifactSkeleton />
              </div>
            ) : (
              <ArtifactEmptyState
                title={t("sessions.context.artifacts.emptyTitle", { defaultValue: "No artifacts in this conversation yet" })}
                description={t("sessions.context.artifacts.emptyDescription", {
                  defaultValue:
                    "When the agent creates links, images, documents or other outputs, they will appear here with rich previews and execution context.",
                })}
              />
            )
          ) : (
            <div className="space-y-5">
              {groupedArtifacts.map(([group, items]) => (
                <section key={group}>
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-quaternary)]">{group}</p>
                    <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-hover)] px-2.5 py-1 text-[10px] font-medium text-[var(--text-tertiary)]">
                      {items.length}
                    </span>
                  </div>
                  <div className="space-y-3">
                    {items.map((artifact) => (
                      <ArtifactCard
                        key={artifact.dedupeKey}
                        artifact={artifact}
                        preview={artifact.url ? (linkPreviewByUrl.get(artifact.url) ?? null) : null}
                        t={t}
                      />
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </div>

        <div className="mt-6 grid grid-cols-2 gap-3">
          <MetaBlock
            label={t("sessions.context.messages", { defaultValue: "Messages" })}
            value={detail.totals.messages}
          />
          <MetaBlock
            label={t("sessions.context.executions", { defaultValue: "Executions" })}
            value={detail.totals.executions}
          />
          <MetaBlock
            label={t("sessions.context.tools", { defaultValue: "Tools" })}
            value={detail.totals.tools}
          />
          <MetaBlock
            label={t("sessions.context.cost", { defaultValue: "Cost" })}
            value={formatCost(detail.totals.cost_usd)}
          />
        </div>

        <div className="mt-5 space-y-3 rounded-[1.25rem] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] p-4">
          <div>
            <p className="text-[10px] uppercase tracking-[0.16em] text-[var(--text-quaternary)]">
              {t("sessions.context.createdAt", { defaultValue: "Created" })}
            </p>
            <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
              {summary.created_at ? formatRelativeTime(summary.created_at) : "—"}
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.16em] text-[var(--text-quaternary)]">
              {t("sessions.context.lastActivity", { defaultValue: "Last activity" })}
            </p>
            <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
              {summary.last_activity_at ? formatRelativeTime(summary.last_activity_at) : "—"}
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.16em] text-[var(--text-quaternary)]">
              {t("sessions.context.sessionId", { defaultValue: "Session ID" })}
            </p>
            <p className="mt-1 break-all font-mono text-[12px] text-[var(--text-secondary)]">
              {summary.session_id}
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.16em] text-[var(--text-quaternary)]">
              {t("sessions.context.userId", { defaultValue: "User ID" })}
            </p>
            <p className="mt-1 font-mono text-[12px] text-[var(--text-secondary)]">
              {summary.user_id ?? "—"}
            </p>
          </div>
        </div>

        <div className="mt-5">
          <div className="mb-3 flex items-center gap-2">
            <MessageSquareText className="h-4 w-4 text-[var(--text-tertiary)]" />
            <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
              {t("sessions.context.recentExecutions", { defaultValue: "Recent executions" })}
            </p>
          </div>

          {recentExecutions.length === 0 ? (
            <div className="rounded-[1.1rem] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-4 py-4 text-sm text-[var(--text-tertiary)]">
              {t("sessions.context.noExecutions", { defaultValue: "No linked executions yet." })}
            </div>
          ) : (
            <div className="space-y-2.5">
              {recentExecutions.map((execution) => (
                <div
                  key={execution.task_id}
                  className="rounded-[1.05rem] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-3.5 py-3"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-[13px] font-medium text-[var(--text-primary)]">
                        #{execution.task_id}{" "}
                        {execution.query_text
                          ? truncateText(execution.query_text, 40)
                          : t("sessions.context.artifacts.executionFallback", { defaultValue: "Execution" })}
                      </p>
                      <p className="mt-1 truncate text-[12px] text-[var(--text-tertiary)]">
                        {execution.model || "—"} •{" "}
                        {formatRelativeTime(execution.completed_at || execution.started_at || execution.created_at)}
                      </p>
                    </div>
                    <span className="shrink-0 text-[12px] font-semibold text-[var(--text-primary)]">
                      {formatCost(execution.cost_usd)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
