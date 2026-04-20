"use client";

import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
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
import { ContextArtifacts, type SessionArtifactItem } from "./context-artifacts";
import { ContextExecutions } from "./context-executions";
import { ContextSummary } from "./context-summary";

const ARTIFACT_EXECUTION_LIMIT = 12;
const ARTIFACT_LINK_PREVIEW_LIMIT = 8;

type SessionSummaryLike = SessionSummary & { agent_id?: string | null };
type ExecutionSummaryLike = ExecutionSummary & { agent_id?: string | null };

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
    const leftTime = new Date(
      left.completed_at || left.started_at || left.created_at,
    ).getTime();
    const rightTime = new Date(
      right.completed_at || right.started_at || right.created_at,
    ).getTime();
    return rightTime - leftTime;
  });
}

function resolveSummaryBotId(summary: SessionSummary | null | undefined) {
  if (!summary) return null;
  const withAgent = summary as SessionSummaryLike;
  return withAgent.bot_id || withAgent.agent_id || null;
}

function buildArtifactItems(
  executionDetails: Array<{ execution: ExecutionSummaryLike; detail: ExecutionDetail }>,
) {
  const items: SessionArtifactItem[] = [];
  const seen = new Set<string>();
  const sorted = [...executionDetails].sort((left, right) => {
    const leftTime = new Date(
      left.execution.completed_at ||
        left.execution.started_at ||
        left.execution.created_at,
    ).getTime();
    const rightTime = new Date(
      right.execution.completed_at ||
        right.execution.started_at ||
        right.execution.created_at,
    ).getTime();
    return rightTime - leftTime;
  });

  for (const item of sorted) {
    for (const artifact of item.detail.artifacts) {
      if (
        artifact.kind === "text" &&
        artifact.source_type === "assistant_response" &&
        !artifact.url
      ) {
        continue;
      }
      const dedupeKey =
        artifact.url || artifact.path || `${item.detail.task_id}:${artifact.id}`;
      if (seen.has(dedupeKey)) continue;
      seen.add(dedupeKey);
      items.push({
        ...artifact,
        execution: item.execution,
        activityAt:
          item.execution.completed_at ||
          item.execution.started_at ||
          item.execution.created_at,
        dedupeKey,
      });
    }
  }

  return items;
}

function resolveModelLabel(detail: SessionDetail | null): string | null {
  if (!detail) return null;
  for (let index = detail.messages.length - 1; index >= 0; index -= 1) {
    const message = detail.messages[index];
    const model =
      message.model?.trim() || message.linked_execution?.model?.trim() || null;
    if (model) return model;
  }
  return null;
}

interface SessionContextPanelProps {
  detail: SessionDetail | null;
  summary: SessionSummary | null;
  className?: string;
  onOpenExecution?: (taskId: number, agentId: string | null) => void;
}

export function SessionContextPanel({
  detail,
  summary,
  className,
  onOpenExecution,
}: SessionContextPanelProps) {
  const { t } = useAppI18n();
  const { agents } = useAgentCatalog();
  const fallbackExecutions = useMemo(() => dedupeExecutions(detail), [detail]);
  const sessionBotId =
    resolveSummaryBotId(summary) || resolveSummaryBotId(detail?.summary ?? null);
  const sessionId = summary?.session_id || detail?.summary.session_id || null;
  const activeAgent = sessionBotId
    ? agents.find((entry) => entry.id === sessionBotId) ?? null
    : null;
  const modelLabel = useMemo(() => resolveModelLabel(detail), [detail]);

  const executionsQuery = useControlPlaneQuery<{ items: ExecutionSummaryLike[] }>({
    tier: "live",
    queryKey: queryKeys.dashboard.executions({
      agentIds: sessionBotId ? [sessionBotId] : [],
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
          params: { sessionId, limit: ARTIFACT_EXECUTION_LIMIT },
          fallbackError: t("sessions.loadError"),
        },
      );
      return {
        items:
          Array.isArray(response.data) && response.data.length > 0
            ? response.data
            : fallbackExecutions.slice(0, ARTIFACT_EXECUTION_LIMIT),
      };
    },
  });

  const executions = useMemo(() => {
    if (executionsQuery.data?.items?.length) return executionsQuery.data.items;
    return fallbackExecutions.slice(0, ARTIFACT_EXECUTION_LIMIT);
  }, [executionsQuery.data?.items, fallbackExecutions]);

  const executionDetailsQueries = useQueries({
    queries: executions.map((execution) => {
      const executionBotId =
        execution.bot_id || (execution as ExecutionSummaryLike).agent_id || null;
      return {
        queryKey: queryKeys.dashboard.executionDetail(
          executionBotId ?? "",
          execution.task_id,
        ),
        enabled: Boolean(executionBotId),
        staleTime: 30_000,
        queryFn: async ({ signal }: { signal: AbortSignal }) => {
          if (!executionBotId) throw new Error(t("sessions.loadError"));
          return fetchControlPlaneDashboardJson<ExecutionDetail>(
            `/agents/${executionBotId}/executions/${execution.task_id}`,
            { signal, fallbackError: t("sessions.loadError") },
          );
        },
      };
    }),
  });

  const executionDetails = useMemo(
    () =>
      executionDetailsQueries.flatMap((result, index) =>
        result.data ? [{ execution: executions[index], detail: result.data }] : [],
      ),
    [executionDetailsQueries, executions],
  );

  const artifactItems = useMemo(
    () => buildArtifactItems(executionDetails),
    [executionDetails],
  );

  const linkArtifacts = useMemo(
    () =>
      artifactItems
        .filter((artifact: ExecutionArtifact) => artifact.kind === "url" && artifact.url)
        .slice(0, ARTIFACT_LINK_PREVIEW_LIMIT),
    [artifactItems],
  );

  const linkPreviewQueries = useQueries({
    queries: linkArtifacts.map((artifact) => ({
      queryKey: ["dashboard", "link-preview", artifact.url] as const,
      enabled: Boolean(artifact.url),
      staleTime: 10 * 60_000,
      queryFn: async ({ signal }: { signal: AbortSignal }) => {
        const response =
          await fetchControlPlaneDashboardJsonAllowError<ExecutionArtifactLinkPreview>(
            "/link-preview",
            {
              signal,
              params: { url: artifact.url },
              fallbackError: t("sessions.context.artifacts.previewUnavailable", {
                defaultValue: "Link preview is unavailable.",
              }),
            },
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

  if (!summary || !detail) {
    return (
      <aside
        className={`flex h-full min-h-0 flex-col items-center justify-center px-6 text-center ${className ?? ""}`}
      >
        <p className="m-0 text-[var(--font-size-sm)] text-[var(--text-tertiary)]">
          {t("sessions.context.emptyDescription", {
            defaultValue: "Select a conversation to inspect its details.",
          })}
        </p>
      </aside>
    );
  }

  return (
    <aside
      className={`flex h-full min-h-0 flex-col divide-y divide-[color:var(--divider-hair)] ${className ?? ""}`}
    >
      <ContextSummary
        summary={summary}
        detail={detail}
        agentLabel={activeAgent?.label ?? sessionBotId ?? null}
        agentColor={activeAgent?.color ?? null}
        modelLabel={modelLabel}
      />
      <ContextExecutions
        executions={executions}
        onOpenExecution={onOpenExecution}
      />
      <ContextArtifacts items={artifactItems} linkPreviewByUrl={linkPreviewByUrl} />
    </aside>
  );
}
