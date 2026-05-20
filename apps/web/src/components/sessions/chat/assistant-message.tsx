"use client";

import { useEffect, useState } from "react";
import { SessionRichText } from "@/components/sessions/session-rich-text";
import { ReasoningBlock } from "@/components/sessions/chat/reasoning-block";
import { ToolCallCard } from "@/components/sessions/chat/tool-call-card";
import { ApprovalPrompt } from "@/components/sessions/chat/approval-prompt";
import { BlockRenderer } from "@/components/sessions/chat/generative/block-renderer";
import { InlineArtifactList } from "@/components/sessions/artifacts/inline-artifact-list";
import { fetchControlPlaneDashboardJson } from "@/lib/control-plane-dashboard";
import type { PendingApproval } from "@/lib/contracts/sessions";
import { formatDuration } from "@/lib/utils";
import type { ExecutionArtifact, ExecutionSummary } from "@/lib/types";

interface AssistantMessageProps {
  text: string;
  linkedExecution?: ExecutionSummary | null;
  extraExecutions?: ExecutionSummary[];
  onOpenExecution?: (taskId: number) => void;
  agentId?: string | null;
  sessionId?: string | null;
  artifacts?: ExecutionArtifact[];
  blocks?: unknown[];
  /** Forwarded by interactive blocks (M6). */
  onBlockAction?: (blockId: string, actionId: string) => void;
}

function collectReasoningLines(execution: ExecutionSummary | null | undefined): string[] {
  if (!execution) return [];
  const maybeReasoning = (execution as { reasoning_summary?: unknown }).reasoning_summary;
  if (Array.isArray(maybeReasoning)) {
    const lines = (maybeReasoning as unknown[]).filter(
      (line): line is string => typeof line === "string" && line.trim().length > 0,
    );
    if (lines.length > 0) return lines;
  }
  const gateReasons = execution.answer_gate_reasons ?? [];
  if (gateReasons.length > 0) return gateReasons;
  return [];
}

export function AssistantMessage({
  text,
  linkedExecution,
  extraExecutions = [],
  onOpenExecution,
  agentId,
  sessionId,
  artifacts = [],
  blocks,
  onBlockAction,
}: AssistantMessageProps) {
  const reasoning = collectReasoningLines(linkedExecution);
  const hasReasoning = reasoning.length > 0;
  const durationLabel =
    linkedExecution?.duration_ms && linkedExecution.duration_ms > 0
      ? formatDuration(linkedExecution.duration_ms)
      : null;
  const streaming =
    linkedExecution?.status === "running" || linkedExecution?.status === "retrying";

  const pendingApprovalId = linkedExecution?.pending_approval_id ?? null;
  const approvalReasons = linkedExecution?.answer_gate_reasons ?? [];
  const [pendingApprovalState, setPendingApprovalState] = useState<{
    approvalId: string | null;
    approval: PendingApproval | null;
  }>({ approvalId: null, approval: null });
  const pendingApproval =
    pendingApprovalState.approvalId === pendingApprovalId ? pendingApprovalState.approval : null;

  useEffect(() => {
    let cancelled = false;
    if (!agentId || !pendingApprovalId) return () => undefined;
    void fetchControlPlaneDashboardJson<{ items: PendingApproval[] }>(
      `/agents/${encodeURIComponent(agentId)}/approvals`,
      { fallbackError: "Unable to load pending approvals" },
    )
      .then((response) => {
        if (cancelled) return;
        setPendingApprovalState({
          approvalId: pendingApprovalId,
          approval: response.items.find((approval) => approval.approval_id === pendingApprovalId) ?? null,
        });
      })
      .catch(() => {
        if (!cancelled) {
          setPendingApprovalState({ approvalId: pendingApprovalId, approval: null });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [agentId, pendingApprovalId]);

  return (
    <div className="flex flex-col gap-3">
      {hasReasoning || streaming ? (
        <ReasoningBlock streaming={streaming} durationLabel={durationLabel}>
          {hasReasoning ? (
            <ul className="m-0 list-disc space-y-1 pl-4">
              {reasoning.map((line, index) => (
                <li key={index}>{line}</li>
              ))}
            </ul>
          ) : (
            <p className="m-0">…</p>
          )}
        </ReasoningBlock>
      ) : null}

      {text.trim() ? (
        <div className="text-[var(--font-size-md)] leading-[1.6] text-[var(--text-primary)]">
          <SessionRichText content={text} variant="assistant" />
        </div>
      ) : null}

      {blocks && blocks.length > 0 ? (
        <div className="flex flex-col gap-3">
          {blocks.map((raw, index) => {
            const id =
              (raw && typeof raw === "object" && "id" in raw && typeof raw.id === "string"
                ? raw.id
                : null) ?? `block-${index}`;
            return (
              <BlockRenderer
                key={id}
                raw={raw}
                onAction={onBlockAction}
                agentId={agentId}
                sessionId={sessionId}
              />
            );
          })}
        </div>
      ) : null}

      <InlineArtifactList
        artifacts={artifacts}
        agentId={agentId}
        activityAt={linkedExecution?.completed_at || linkedExecution?.started_at || null}
      />

      {linkedExecution ? (
        <ToolCallCard execution={linkedExecution} onOpenDetails={onOpenExecution} />
      ) : null}

      {pendingApprovalId && agentId && sessionId ? (
        <ApprovalPrompt
          agentId={agentId}
          sessionId={sessionId}
          approvalId={pendingApprovalId}
          toolName={pendingApproval?.tool_id ?? pendingApproval?.tool_name ?? linkedExecution?.query_text ?? null}
          reasons={approvalReasons}
          preview={pendingApproval?.preview_text ?? null}
          schema={pendingApproval?.args_schema ?? pendingApproval?.schema ?? null}
          originalParams={pendingApproval?.original_params ?? pendingApproval?.params ?? null}
        />
      ) : null}

      {extraExecutions.length > 0 ? (
        <div className="flex flex-col">
          {extraExecutions.map((execution) => (
            <ToolCallCard
              key={execution.task_id}
              execution={execution}
              onOpenDetails={onOpenExecution}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
