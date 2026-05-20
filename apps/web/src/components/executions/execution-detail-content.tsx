"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Copy,
  FileCheck2,
} from "lucide-react";
import type {
  ExecutionArtifact,
  ExecutionDetail,
  ExecutionSummary,
  ExecutionTimelineItem,
  ExecutionToolTrace,
} from "@/lib/types";
import {
  cn,
  formatCost,
  formatDateTime,
  formatDuration,
  formatRelativeTime,
} from "@/lib/utils";
import {
  getSemanticIconStyle,
  getSemanticStrongStyle,
  getSemanticStyle,
  getSemanticTextStyle,
  type SemanticTone,
} from "@/lib/theme-semantic";
import { DetailRow } from "../shared/detail-row";
import { DetailsViewer } from "../audit/details-viewer";
import { SyntaxHighlight, type SyntaxLang } from "../shared/syntax-highlight";
import {
  ChildRunsPanel,
  ContextGovernancePanel,
  RunGraphSummaryPanel,
  RunGraphViewer,
  RunReplayPanel,
} from "@/components/runtime/run-graph-panels";
import { parseContextGovernancePayload } from "@/lib/contracts/phase3-runtime";
import { parseRunGraphSnapshot, parseRunReplayPlan } from "@/lib/contracts/run-graph";
import { evalErrorMessage } from "@/lib/contracts/evals";
import { requestJson } from "@/lib/http-client";
import { getCurrentLanguage, translate } from "@/lib/i18n";
import {
  getArtifactVisual,
  getExecutionMetadataVisual,
  getTimelineVisual,
  getToolVisual,
  type RuntimeVisualDescriptor,
} from "@/lib/runtime-visual-taxonomy";

export const EXECUTION_TRACE_SOURCE_META: Record<
  ExecutionDetail["trace_source"],
  { labelKey: string; descriptionKey: string; tone: SemanticTone }
> = {
  trace: {
    labelKey: "executions.detail.traceRich",
    descriptionKey: "executions.detail.traceRichDescription",
    tone: "success",
  },
  legacy: {
    labelKey: "executions.detail.reconstructed",
    descriptionKey: "executions.detail.reconstructedDescription",
    tone: "warning",
  },
  missing: {
    labelKey: "executions.detail.noTrace",
    descriptionKey: "executions.detail.noTraceDescription",
    tone: "neutral",
  },
};

export const EXECUTION_RESPONSE_SOURCE_META: Record<
  ExecutionDetail["response_source"],
  { labelKey: string; tone: SemanticTone }
> = {
  trace: {
    labelKey: "executions.detail.responseFromTrace",
    tone: "success",
  },
  queries: {
    labelKey: "executions.detail.responseFallbackQueries",
    tone: "warning",
  },
  missing: {
    labelKey: "executions.detail.noResponse",
    tone: "neutral",
  },
};

export const EXECUTION_TOOLS_SOURCE_META: Record<
  ExecutionDetail["tools_source"],
  { labelKey: string; tone: SemanticTone }
> = {
  trace: {
    labelKey: "executions.detail.structuredTools",
    tone: "success",
  },
  audit: {
    labelKey: "executions.detail.legacyTools",
    tone: "warning",
  },
  missing: {
    labelKey: "executions.detail.noTools",
    tone: "neutral",
  },
};

const TIMELINE_TONE: Record<
  ExecutionTimelineItem["status"],
  SemanticTone
> = {
  info: "info",
  success: "success",
  warning: "warning",
  error: "danger",
};

const TOOL_METADATA_HIDDEN_KEYS = new Set([
  "category",
  "sql",
  "env",
  "max_rows",
  "analyze",
  "binary",
  "args",
  "exit_code",
  "timed_out",
  "truncated",
]);

type ExecutionDetailVariant = "panel" | "drawer" | "expanded";

interface ExecutionDetailContentProps {
  data: ExecutionDetail;
  detailLoaded?: boolean;
  loading?: boolean;
  error?: string | null;
  variant?: ExecutionDetailVariant;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function readNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function readBoolean(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function hasEntries(value: Record<string, unknown>): boolean {
  return Object.keys(value).length > 0;
}

function toViewerRecord(
  value: ExecutionArtifact["content"] | Record<string, unknown>
): Record<string, unknown> {
  if (Array.isArray(value)) return { items: value };
  if (isRecord(value)) return value;
  return { value };
}

function getToolCommand(tool: ExecutionToolTrace): string | null {
  const binary = readString(tool.metadata.binary);
  const args = readString(tool.metadata.args);
  if (binary && args) return `${binary} ${args}`.trim();
  if (binary) return binary;
  if (args) return args;
  return null;
}

function getToolExtraMetadata(tool: ExecutionToolTrace): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(tool.metadata).filter(([key]) => !TOOL_METADATA_HIDDEN_KEYS.has(key))
  );
}

export function copyExecutionValue(value: unknown) {
  if (value == null) return;
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  void navigator.clipboard?.writeText(text);
}

export function getExecutionDisplayDetail(
  execution: ExecutionSummary | null,
  detail: ExecutionDetail | null
): ExecutionDetail | null {
  if (detail && (!execution || detail.task_id === execution.task_id)) return detail;
  if (!execution) return null;

  return {
    task_id: execution.task_id,
    bot_id: execution.bot_id,
    status: execution.status,
    query_text: execution.query_text,
    response_text: null,
    model: execution.model,
    session_id: execution.session_id,
    work_dir: null,
    user_id: execution.user_id,
    chat_id: execution.chat_id,
    created_at: execution.created_at,
    started_at: execution.started_at,
    completed_at: execution.completed_at,
    cost_usd: execution.cost_usd,
    duration_ms: execution.duration_ms,
    attempt: execution.attempt,
    max_attempts: execution.max_attempts,
    error_message: execution.error_message,
    stop_reason: execution.stop_reason,
    warnings: [],
    has_rich_trace: execution.has_rich_trace,
    trace_source: execution.trace_source,
    response_source: "missing",
    tools_source: "missing",
    tool_count: execution.tool_count,
    timeline: [],
    tools: [],
    reasoning_summary: [],
    artifacts: [],
    redactions: null,
  };
}

export function ExecutionSourceBadge({
  meta,
}: {
  meta: { labelKey: string; tone: SemanticTone };
}) {
  return (
    <span
      className="inline-flex max-w-full whitespace-normal break-words rounded-lg border px-2.5 py-1 text-left text-[10px] font-semibold leading-4 tracking-[0.04em]"
      style={getSemanticStyle(meta.tone)}
    >
      {translate(meta.labelKey)}
    </span>
  );
}

function formatCompactDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat(getCurrentLanguage(), {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).format(new Date(iso));
}

interface ExecutionDataStripItem {
  label: string;
  value: ReactNode;
  title?: string;
  mono?: boolean;
  wrap?: boolean;
  visual?: RuntimeVisualDescriptor;
}

function ExecutionDataStrip({
  items,
  cols,
  variant = "drawer",
  minItemWidth,
}: {
  items: ExecutionDataStripItem[];
  cols: 2 | 3 | 4 | 5;
  variant?: ExecutionDetailVariant;
  minItemWidth?: number;
}) {
  const defaultMinWidth =
    minItemWidth ??
    (variant === "expanded"
      ? cols >= 4
        ? 156
        : 180
      : variant === "panel"
        ? cols >= 4
          ? 168
          : 176
      : cols >= 4
        ? 214
        : 176);
  return (
    <div className="overflow-hidden rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--divider-hair)]">
      <div
        className="grid gap-px"
        style={{
          gridTemplateColumns: `repeat(auto-fit, minmax(${defaultMinWidth}px, 1fr))`,
        }}
      >
        {items.map((item) => {
          const visual = item.visual;
          const Icon = visual?.icon;
          const shouldWrap = item.wrap || typeof item.value !== "string";
          return (
            <div
              key={item.label}
              className="flex min-w-0 items-start gap-2.5 bg-[var(--panel-soft)] px-3.5 py-3"
              data-metadata-visual={visual?.key}
            >
              {Icon ? (
                <span
                  className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border"
                  style={getSemanticIconStyle(visual.tone)}
                  title={visual.label}
                >
                  <Icon className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
                </span>
              ) : null}
              <span className="flex min-w-0 flex-1 flex-col gap-1">
                <span className="break-words font-mono text-[10px] font-medium uppercase leading-4 tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
                  {item.label}
                </span>
                <span
                  title={item.title}
                  className={cn(
                    "block min-w-0 max-w-full text-[0.8125rem] leading-5 text-[var(--text-primary)]",
                    shouldWrap ? "whitespace-normal break-words [&>*]:max-w-full" : "truncate",
                    item.mono && "font-mono tabular-nums",
                  )}
                >
                  {item.value}
                </span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function ExecutionDetailContent({
  data,
  detailLoaded = false,
  loading = false,
  error,
  variant = "drawer",
}: ExecutionDetailContentProps) {
  const isExpanded = variant === "expanded";
  const isPanel = variant === "panel";
  const traceSource = EXECUTION_TRACE_SOURCE_META[data.trace_source];
  const responseSource = EXECUTION_RESPONSE_SOURCE_META[data.response_source];
  const toolsSource = EXECUTION_TOOLS_SOURCE_META[data.tools_source];
  const runGraph = parseRunGraphSnapshot(data.run_graph ?? null);
  const runReplay = parseRunReplayPlan(data.run_replay ?? null) ?? runGraph?.replay ?? null;
  const contextGovernance = parseContextGovernancePayload(data.context_governance ?? null);
  const [evalCreateState, setEvalCreateState] = useState<{
    status: "idle" | "pending" | "success" | "error";
    message: string | null;
  }>({ status: "idle", message: null });

  async function createEvalFromRun() {
    setEvalCreateState({ status: "pending", message: null });
    try {
      await requestJson<unknown>(
        `/api/control-plane/agents/${encodeURIComponent(data.bot_id)}/evals/cases/from-run`,
        {
          method: "POST",
          body: JSON.stringify({
            task_id: data.task_id,
            source_task_id: data.task_id,
            run_id: `task:${data.task_id}`,
            title: `Execution #${data.task_id}`,
            input_preview: data.query_text ?? "",
            expected_output_preview: data.response_text ?? "",
            reference_answer: data.response_text ?? "",
            status: "draft",
          }),
        },
      );
      setEvalCreateState({
        status: "success",
        message: translate("generated.executions.eval_case_created_4e159649"),
      });
    } catch (caught) {
      setEvalCreateState({
        status: "error",
        message:
          caught instanceof Error && caught.message.trim()
            ? caught.message
            : evalErrorMessage(caught, translate("generated.executions.could_not_create_eval_case_7d94f6ec")),
      });
    }
  }

  if (loading && !detailLoaded) {
    return (
      <div className={cn("space-y-4", isExpanded && "space-y-5")}>
        {Array.from({ length: isExpanded ? 5 : 4 }).map((_, index) => (
          <div key={index} className="glass-card-sm space-y-3 p-5">
            <div className="skeleton skeleton-text w-28" />
            <div className="skeleton skeleton-heading w-full" />
            <div className="skeleton skeleton-text w-3/4" />
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <NoticeCard
        icon={AlertTriangle}
        tone="error"
        title={translate("executions.detail.loadErrorTitle")}
        description={error}
        variant={variant}
      />
    );
  }

  const metrics = (
    <ExecutionDataStrip
      cols={5}
      variant={variant}
      minItemWidth={variant === "drawer" ? 154 : undefined}
      items={[
        { label: translate("common.cost"), value: formatCost(data.cost_usd), mono: true, visual: getExecutionMetadataVisual("cost") },
        { label: translate("common.duration"), value: formatDuration(data.duration_ms), mono: true, visual: getExecutionMetadataVisual("duration") },
        { label: translate("common.attempts"), value: `${data.attempt}/${data.max_attempts}`, mono: true, visual: getExecutionMetadataVisual("attempts") },
        { label: translate("common.tools"), value: String(data.tool_count), mono: true, visual: getExecutionMetadataVisual("tools") },
        { label: translate("common.warnings"), value: String(data.warnings.length), mono: true, visual: getExecutionMetadataVisual("warnings") },
      ]}
    />
  );

  const notices = (
    <>
      {traceSource && data.trace_source !== "trace" && (
        <NoticeCard
          icon={AlertTriangle}
          tone="warning"
          title={translate(traceSource.labelKey)}
          variant={variant}
        />
      )}
      {data.error_message && (
        <NoticeCard
          icon={AlertTriangle}
          tone="error"
          title={translate("executions.detail.failureRecorded")}
          description={data.error_message}
          copyValue={data.error_message}
          variant={variant}
        />
      )}
      {data.warnings.length > 0 && (
        <WarningsPanel warnings={data.warnings} variant={variant} />
      )}
      {evalCreateState.status === "error" && evalCreateState.message ? (
        <NoticeCard
          icon={AlertTriangle}
          tone="error"
          title={translate("generated.executions.eval_case_creation_failed_3abed341")}
          description={evalCreateState.message}
          variant={variant}
        />
      ) : null}
    </>
  );

  const stopReasonLabel =
    data.stop_reason ?? translate("executions.detail.notProvided");

  const timelineStrip = (
    <ExecutionDataStrip
      cols={3}
      variant={variant}
      minItemWidth={variant === "drawer" ? 184 : undefined}
      items={[
        {
          label: translate("common.createdAt", {
            defaultValue: translate("generated.executions.criada_em_90f4965a"),
          }),
          value: formatCompactDateTime(data.created_at),
          title: formatDateTime(data.created_at),
          mono: true,
          visual: getExecutionMetadataVisual("created_at"),
        },
        {
          label: translate("common.startedAt"),
          value: formatCompactDateTime(data.started_at),
          title: formatDateTime(data.started_at),
          mono: true,
          visual: getExecutionMetadataVisual("started_at"),
        },
        {
          label: translate("common.completedAt"),
          value: formatCompactDateTime(data.completed_at),
          title: formatDateTime(data.completed_at),
          mono: true,
          visual: getExecutionMetadataVisual("completed_at"),
        },
      ]}
    />
  );

  const summarySection = (
    <DetailSection
      title={translate("executions.detail.signals")}
      variant={variant}
      action={
        <div className="flex flex-wrap items-center justify-end gap-2">
          {evalCreateState.status === "success" ? (
            <Link
              href={`/evaluations?agent=${encodeURIComponent(data.bot_id)}`}
              className="button-shell button-shell--secondary button-shell--sm inline-flex px-3"
            >
              {translate("generated.executions.open_evals_3abc3a4a")}
            </Link>
          ) : null}
          <button
            type="button"
            onClick={() => {
              void createEvalFromRun();
            }}
            disabled={evalCreateState.status === "pending"}
            className="button-shell button-shell--secondary button-shell--sm gap-2 px-3"
          >
            <FileCheck2 className="h-3.5 w-3.5" />
            {evalCreateState.status === "pending"
              ? translate("generated.executions.creating_eval_8f0b4632")
              : evalCreateState.status === "success"
                ? translate("generated.executions.eval_created_75820127")
                : translate("generated.executions.create_eval_c5f9d9d9")}
          </button>
          <Link
            href={`/runtime/${data.bot_id}/tasks/${data.task_id}`}
            className="button-shell button-shell--primary button-shell--sm inline-flex px-3"
          >
            {translate("executions.detail.openRuntimeRoom")}
          </Link>
        </div>
      }
    >
      <ExecutionDataStrip
        cols={4}
        variant={variant}
        minItemWidth={variant === "drawer" ? 220 : undefined}
        items={[
          {
            label: translate("executions.detail.traceSource"),
            value: <ExecutionSourceBadge meta={traceSource} />,
            visual: getExecutionMetadataVisual("trace_source"),
          },
          {
            label: translate("executions.detail.responseSource"),
            value: <ExecutionSourceBadge meta={responseSource} />,
            visual: getExecutionMetadataVisual("response_source"),
          },
          {
            label: translate("executions.detail.toolsSource"),
            value: <ExecutionSourceBadge meta={toolsSource} />,
            visual: getExecutionMetadataVisual("tools_source"),
          },
          {
            label: translate("executions.detail.stopReason"),
            value: stopReasonLabel,
            title: stopReasonLabel,
            mono: true,
            wrap: true,
            visual: getExecutionMetadataVisual("stop_reason"),
          },
        ]}
      />
    </DetailSection>
  );

  const runGraphSection = (
    <DetailSection title={translate("generated.executions.rungraph_1d9c778c")} variant={variant}>
      <div className="space-y-4">
        <RunGraphSummaryPanel
          graph={runGraph}
          replay={runReplay}
          runtimeHref={`/runtime/${data.bot_id}/tasks/${data.task_id}`}
          variant="inline"
        />
        <RunGraphViewer graph={runGraph} variant="inline" />
        <ChildRunsPanel
          agentId={data.bot_id}
          childRuns={data.child_runs ?? []}
          variant="inline"
        />
        <ContextGovernancePanel context={contextGovernance} variant="inline" />
        <RunReplayPanel replay={runReplay} variant="inline" />
      </div>
    </DetailSection>
  );

  const entrySection = (
    <DetailSection
      title={translate("executions.detail.input")}
      variant={variant}
    >
      <CodePanel
        title={translate("common.message")}
        content={data.query_text}
        onCopy={() => copyExecutionValue(data.query_text)}
        variant={variant}
      />
      <div className="mt-4">
        <ExecutionDataStrip
          cols={2}
          variant={variant}
          minItemWidth={variant === "drawer" ? 260 : undefined}
          items={[
            {
              label: translate("common.model"),
              value: data.model ?? "—",
              title: data.model ?? undefined,
              mono: true,
              wrap: true,
              visual: getExecutionMetadataVisual("model"),
            },
            {
              label: translate("common.session"),
              value: data.session_id ?? "—",
              title: data.session_id ?? undefined,
              mono: true,
              wrap: true,
              visual: getExecutionMetadataVisual("session"),
            },
            {
              label: translate("common.workspaceDirectory"),
              value: data.work_dir ?? "—",
              title: data.work_dir ?? undefined,
              mono: true,
              wrap: true,
              visual: getExecutionMetadataVisual("workspace"),
            },
            {
              label: translate("generated.executions.user_chat_30653443"),
              value: `${data.user_id} / ${data.chat_id}`,
              mono: true,
              wrap: true,
              visual: getExecutionMetadataVisual("actor"),
            },
          ]}
        />
      </div>
    </DetailSection>
  );

  const responseSection = data.response_text ? (
    <DetailSection title={translate("executions.detail.output")} variant={variant}>
      <CodePanel
        title={translate("executions.detail.response")}
        content={data.response_text}
        onCopy={() => copyExecutionValue(data.response_text)}
        mono={false}
        badge={<ExecutionSourceBadge meta={responseSource} />}
        variant={variant}
      />
    </DetailSection>
  ) : null;

  const toolsSection = data.tools.length > 0 ? (
    <DetailSection title={translate("executions.detail.steps")} variant={variant}>
      <div className="space-y-4">
        {data.tools.map((tool) => (
          <ToolCard key={tool.id} tool={tool} variant={variant} />
        ))}
      </div>
    </DetailSection>
  ) : null;

  const timelineSection = data.timeline.length > 0 ? (
    <DetailSection title={translate("executions.detail.activity")} variant={variant}>
      <div className="space-y-3">
        {data.timeline.map((item) => (
          <TimelineCard key={item.id} item={item} variant={variant} />
        ))}
      </div>
    </DetailSection>
  ) : null;

  const reasoningSection = data.reasoning_summary.length > 0 ? (
    <DetailSection title={translate("executions.detail.notes")} variant={variant}>
      <div className="space-y-3">
        {data.reasoning_summary.map((line, index) => (
          <div
            key={`${line}-${index}`}
            className={cn(
              "border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] text-sm leading-6 text-[var(--text-secondary)] shadow-none",
              isExpanded ? "rounded-lg px-4 py-3.5" : "rounded-lg px-3.5 py-3"
            )}
          >
            <span className="mr-2 font-mono text-[10px] text-[var(--text-quaternary)]">
              {(index + 1).toString().padStart(2, "0")}
            </span>
            {line}
          </div>
        ))}
      </div>
    </DetailSection>
  ) : null;

  const artifactsSection = data.artifacts.length > 0 ? (
    <DetailSection title={translate("executions.detail.files")} variant={variant}>
      <div className="space-y-4">
        {data.artifacts.map((artifact) => (
          <ArtifactCard key={artifact.id} artifact={artifact} variant={variant} />
        ))}
      </div>
    </DetailSection>
  ) : null;

  if (!isExpanded) {
    return (
      <div className={cn("space-y-6", isPanel && "space-y-5")}>
        {metrics}
        {timelineStrip}
        {notices}
        {summarySection}
        {runGraphSection}
        {entrySection}
        {timelineSection}
        {toolsSection}
        {responseSection}
        {reasoningSection}
        {artifactsSection}
      </div>
    );
  }

  return (
    <div className="space-y-7">
      {metrics}
      {timelineStrip}
      {summarySection}
      <div className="grid gap-7 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-7">
          {runGraphSection}
          {entrySection}
          {responseSection}
          {toolsSection}
          {artifactsSection}
        </div>
        <aside className="space-y-7">
          {notices}
          {timelineSection}
          {reasoningSection}
        </aside>
      </div>
    </div>
  );
}

function DetailSection({
  title,
  variant,
  children,
  action,
}: {
  title: string;
  variant: ExecutionDetailVariant;
  children: ReactNode;
  action?: ReactNode;
}) {
  const isExpanded = variant === "expanded";
  return (
    <section className={cn("space-y-3.5", isExpanded && "space-y-4")}>
      <div
        className={cn(
          "flex gap-3",
          variant === "drawer"
            ? "flex-col items-stretch sm:flex-row sm:items-center sm:justify-between"
            : "items-center justify-between",
        )}
      >
        <div className="section-label min-w-0 flex-1">
          <span>{title}</span>
        </div>
        {action ? (
          <div className="flex shrink-0 justify-start sm:justify-end">
            {action}
          </div>
        ) : null}
      </div>
      {children}
    </section>
  );
}

function NoticeCard({
  icon: Icon,
  tone,
  title,
  description,
  copyValue: valueToCopy,
  variant,
}: {
  icon: typeof AlertTriangle;
  tone: "warning" | "error";
  title: string;
  description?: string;
  copyValue?: string | null;
  variant: ExecutionDetailVariant;
}) {
  const isWarning = tone === "warning";
  const isExpanded = variant === "expanded";
  const isPanel = variant === "panel";

  return (
    <div
      className={cn(
        "border shadow-none",
        isExpanded ? "rounded-lg p-5" : isPanel ? "rounded-lg p-4" : "rounded-lg p-4"
      )}
      style={getSemanticStyle(isWarning ? "warning" : "danger")}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span
            className={cn(
              "inline-flex items-center justify-center border",
              isExpanded ? "h-9 w-9 rounded-lg" : isPanel ? "h-8 w-8 rounded-lg" : "h-[34px] w-[34px] rounded-lg"
            )}
            style={getSemanticIconStyle(isWarning ? "warning" : "danger")}
          >
            <Icon className="h-4 w-4" />
          </span>
          <div>
            <p className="text-sm font-semibold" style={getSemanticTextStyle(isWarning ? "warning" : "danger")}>
              {title}
            </p>
            {description ? (
              <p
                className={cn("mt-1 leading-6", isExpanded ? "text-sm" : "text-sm")}
                style={getSemanticTextStyle(isWarning ? "warning" : "danger", true)}
              >
                {description}
              </p>
            ) : null}
          </div>
        </div>
        {valueToCopy && (
          <button
            type="button"
            onClick={() => copyExecutionValue(valueToCopy)}
            className="button-shell button-shell--secondary button-shell--sm gap-2 px-3"
          >
            <Copy className="h-3.5 w-3.5" />
            {translate("common.copy")}
          </button>
        )}
      </div>
    </div>
  );
}

function WarningsPanel({
  warnings,
  variant,
}: {
  warnings: string[];
  variant: ExecutionDetailVariant;
}) {
  const isExpanded = variant === "expanded";
  const isPanel = variant === "panel";

  return (
    <div
      className={cn(
        "border shadow-none",
        isExpanded ? "rounded-lg p-5" : isPanel ? "rounded-lg p-4" : "rounded-lg p-3.5"
      )}
      style={getSemanticStyle("warning")}
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-2">
          <span
            className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border"
            style={getSemanticIconStyle("warning")}
          >
            <AlertTriangle className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
          </span>
          <span className="break-words text-[10px] font-semibold uppercase leading-4 tracking-[0.14em]" style={getSemanticTextStyle("warning")}>
            {translate("common.warnings")}
          </span>
        </div>
        <span className="shrink-0 rounded-lg border px-3 py-1 text-[11px] font-semibold" style={getSemanticStrongStyle("warning")}>
          {warnings.length}
        </span>
      </div>
      <ul className="mt-3 space-y-2">
        {warnings.map((warning, index) => (
          <li
            key={`${warning}-${index}`}
            className={cn(
              "list-none break-words border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] text-[13px] leading-6",
              isExpanded ? "rounded-lg px-4 py-3.5" : isPanel ? "rounded-lg px-4 py-3" : "rounded-lg px-3 py-2.5"
            )}
            style={getSemanticStyle("warning")}
          >
            {warning}
          </li>
        ))}
      </ul>
    </div>
  );
}

function TimelineCard({
  item,
  variant,
}: {
  item: ExecutionTimelineItem;
  variant: ExecutionDetailVariant;
}) {
  const visual = getTimelineVisual(item);
  const Icon = visual.icon;
  const tone = TIMELINE_TONE[item.status] ?? visual.tone;
  const isExpanded = variant === "expanded";
  const isPanel = variant === "panel";

  return (
    <div
      className={cn(
        "border shadow-none",
        isExpanded ? "rounded-lg p-5" : isPanel ? "rounded-lg p-4" : "rounded-lg p-4"
      )}
      style={getSemanticStyle(tone)}
      data-timeline-visual={visual.key}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex items-center gap-3">
            <span
              className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border"
              style={getSemanticIconStyle(visual.tone)}
              title={visual.label}
            >
              <Icon className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
            </span>
            <p className="text-sm font-semibold text-[var(--text-primary)]">{item.title}</p>
          </div>
          {item.summary && (
            <p className="text-[13px] leading-6 text-[var(--text-secondary)]">{item.summary}</p>
          )}
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-tertiary)]">
            <span
              className="rounded-lg border px-2.5 py-1 font-mono text-[10px]"
              style={getSemanticStyle(visual.tone)}
            >
              {visual.label}
            </span>
            <span className="rounded-lg border border-[var(--border-subtle)] bg-[var(--field-bg)] px-2.5 py-1 font-mono text-[10px] text-[var(--text-secondary)]">
              {item.type}
            </span>
            <span>{formatDateTime(item.timestamp)}</span>
          </div>
        </div>
        <span className="text-[11px] text-[var(--text-quaternary)]">
          {formatRelativeTime(item.timestamp)}
        </span>
      </div>
      {hasEntries(item.details) && (
        <div className="mt-4">
          <DetailsViewer data={item.details} />
        </div>
      )}
    </div>
  );
}

function ToolCard({
  tool,
  variant,
}: {
  tool: ExecutionToolTrace;
  variant: ExecutionDetailVariant;
}) {
  const visual = getToolVisual({
    tool: tool.tool,
    category: tool.category,
    success: tool.success,
    metadata: tool.metadata,
  });
  const Icon = visual.icon;
  const sql = readString(tool.metadata.sql);
  const env = readString(tool.metadata.env);
  const binary = readString(tool.metadata.binary);
  const args = readString(tool.metadata.args);
  const exitCode = readNumber(tool.metadata.exit_code);
  const timedOut = readBoolean(tool.metadata.timed_out);
  const truncated = readBoolean(tool.metadata.truncated);
  const maxRows = readNumber(tool.metadata.max_rows);
  const analyze = readBoolean(tool.metadata.analyze);
  const command = getToolCommand(tool);
  const extraMetadata = getToolExtraMetadata(tool);
  const isExpanded = variant === "expanded";
  const isPanel = variant === "panel";
  const isDrawer = variant === "drawer";

  return (
    <div
      className={cn(
        "border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] shadow-none",
        isExpanded ? "rounded-lg p-5" : isPanel ? "rounded-lg p-4" : "rounded-lg p-4"
      )}
      data-tool-visual={visual.key}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border"
            style={getSemanticIconStyle(visual.tone)}
            title={visual.label}
          >
            <Icon className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
          </span>
          <div className="min-w-0 space-y-2">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-[var(--text-primary)]">{tool.tool}</p>
              <p className="text-[13px] leading-6 text-[var(--text-secondary)]">{tool.summary}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-tertiary)]">
              <span
                className="rounded-lg border px-2.5 py-1 font-mono text-[10px]"
                style={getSemanticStyle(visual.tone)}
              >
                {visual.label}
              </span>
              <span className="rounded-lg border border-[var(--border-subtle)] bg-[var(--field-bg)] px-2.5 py-1 font-mono text-[10px] text-[var(--text-secondary)]">
                {tool.category}
              </span>
              <span
                className="rounded-lg border px-2.5 py-1 text-[10px] font-semibold"
                style={getSemanticStyle(tool.success === false ? "danger" : "success")}
              >
                {tool.success === false
                  ? translate("common.failed")
                  : translate("toast.success")}
              </span>
              <span className="font-mono">{formatDuration(tool.duration_ms)}</span>
              <span>{formatDateTime(tool.completed_at ?? tool.started_at)}</span>
              {tool.redactions && (
                <span className="rounded-lg border px-2.5 py-1 text-[10px] font-semibold" style={getSemanticStyle("warning")}>
                  {translate("executions.detail.redactions", {
                    count: tool.redactions.count,
                  })}
                </span>
              )}
            </div>
          </div>
        </div>
        {tool.output && (
          <button
            type="button"
            onClick={() => copyExecutionValue(tool.output)}
            className="button-shell button-shell--secondary button-shell--sm gap-2 px-3"
          >
            <Copy className="h-3.5 w-3.5" />
            {translate("generated.executions.copiar_saida_eedddac0")}
          </button>
        )}
      </div>

      <div
        className={cn(
          "mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2",
          isExpanded ? "lg:grid-cols-4" : isPanel ? "xl:grid-cols-2" : isDrawer && "md:grid-cols-2"
        )}
      >
        <DetailRow label={translate("generated.executions.inicio_560f0f5f")}>{formatDateTime(tool.started_at)}</DetailRow>
        <DetailRow label={translate("generated.executions.fim_785edcaa")}>{formatDateTime(tool.completed_at)}</DetailRow>
        <DetailRow label={translate("common.duration")}>
          <span className="font-mono">{formatDuration(tool.duration_ms)}</span>
        </DetailRow>
        <DetailRow label={translate("generated.executions.categoria_18707383")}>
          <span className="font-mono">{tool.category}</span>
        </DetailRow>
      </div>

      {command && (
        <div className="mt-4">
          <CodePanel
            title={binary || args ? translate("generated.executions.comando_cli_61912471") : translate("common.command")}
            content={command}
            onCopy={() => copyExecutionValue(command)}
            lang="shell"
            variant={variant}
          />
        </div>
      )}

      {sql && (
        <div className="mt-4">
          <CodePanel
            title={translate("generated.executions.consulta_sql_ec3df875")}
            content={sql}
            onCopy={() => copyExecutionValue(sql)}
            lang="sql"
            variant={variant}
          />
        </div>
      )}

      <div
        className={cn(
          "mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2",
          isExpanded ? "lg:grid-cols-4" : isPanel ? "xl:grid-cols-2" : isDrawer && "md:grid-cols-2"
        )}
      >
        {env && <DetailRow label={translate("generated.executions.ambiente_60bc9f4d")}>{env}</DetailRow>}
        {maxRows != null && <DetailRow label={translate("generated.executions.limite_de_linhas_44567317")}>{String(maxRows)}</DetailRow>}
        {analyze != null && <DetailRow label={translate("generated.executions.analyze_6c305051")}>{analyze ? translate("generated.executions.sim_4b2e05ee") : translate("generated.executions.nao_41b30e44")}</DetailRow>}
        {exitCode != null && (
          <DetailRow label={translate("generated.executions.codigo_de_saida_84c7b4d4")}>
            <span className="font-mono">{String(exitCode)}</span>
          </DetailRow>
        )}
        {timedOut != null && <DetailRow label={translate("generated.executions.timeout_8e7843bd")}>{timedOut ? translate("generated.executions.sim_4b2e05ee") : translate("generated.executions.nao_41b30e44")}</DetailRow>}
        {truncated != null && <DetailRow label={translate("generated.executions.saida_truncada_d954f55d")}>{truncated ? translate("generated.executions.sim_4b2e05ee") : translate("generated.executions.nao_41b30e44")}</DetailRow>}
      </div>

      {hasEntries(tool.params) && (
        <div className="mt-4">
          <ArtifactShell
            title={translate("generated.executions.parametros_enviados_06cb0ec8")}
            onCopy={() => copyExecutionValue(tool.params)}
            visual={getExecutionMetadataVisual("tools")}
            variant={variant}
          >
            <DetailsViewer data={tool.params} />
          </ArtifactShell>
        </div>
      )}

      {tool.output && (
        <div className="mt-4">
          <CodePanel
            title={translate("generated.executions.saida_da_ferramenta_c234aa09")}
            content={tool.output}
            onCopy={() => copyExecutionValue(tool.output)}
            variant={variant}
          />
        </div>
      )}

      {hasEntries(extraMetadata) && (
        <div className="mt-4">
          <ArtifactShell
            title={translate("generated.executions.metadados_adicionais_a5016a1c")}
            onCopy={() => copyExecutionValue(extraMetadata)}
            visual={getExecutionMetadataVisual("metadata")}
            variant={variant}
          >
            <DetailsViewer data={extraMetadata} />
          </ArtifactShell>
        </div>
      )}
    </div>
  );
}

function ArtifactCard({
  artifact,
  variant,
}: {
  artifact: ExecutionArtifact;
  variant: ExecutionDetailVariant;
}) {
  const content = typeof artifact.content === "string" ? artifact.content : null;
  const visual = getArtifactVisual(artifact.kind);

  return (
    <ArtifactShell
      title={artifact.label}
      onCopy={() => copyExecutionValue(artifact.content)}
      unavailable={artifact.unavailable}
      visual={visual}
      variant={variant}
    >
      {content != null ? (
        <SyntaxHighlight
          className={cn(
            "text-[12px]",
            variant === "expanded"
              ? "p-[18px]"
              : variant === "panel"
                ? "p-3.5"
                : "p-4"
          )}
        >
          {content}
        </SyntaxHighlight>
      ) : (
        <DetailsViewer data={toViewerRecord(artifact.content)} />
      )}
    </ArtifactShell>
  );
}

function ArtifactShell({
  title,
  children,
  onCopy,
  unavailable = false,
  visual,
  variant,
}: {
  title: string;
  children: ReactNode;
  onCopy?: () => void;
  unavailable?: boolean;
  visual?: RuntimeVisualDescriptor;
  variant: ExecutionDetailVariant;
}) {
  const isExpanded = variant === "expanded";
  const isPanel = variant === "panel";
  const Icon = visual?.icon;

  return (
    <div
      className={cn(
        "border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] shadow-none",
        isExpanded ? "rounded-lg p-5" : isPanel ? "rounded-lg p-4" : "rounded-lg p-4"
      )}
    >
      <div className="mb-3 flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-center gap-2">
          {Icon ? (
            <span
              className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border"
              style={getSemanticIconStyle(visual.tone)}
              title={visual.label}
            >
              <Icon className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
            </span>
          ) : null}
          <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
            {title}
          </span>
          {visual ? (
            <span
              className="rounded-md border px-1.5 py-0.5 font-mono text-[0.625rem] uppercase tracking-[0.08em]"
              style={getSemanticStyle(visual.tone)}
            >
              {visual.label}
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          {unavailable && (
            <span className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-2.5 py-1 text-[10px] font-semibold text-[var(--text-tertiary)]">
              {translate("generated.executions.indisponivel_16d4946c")}
            </span>
          )}
          {onCopy && (
            <button
              type="button"
              onClick={onCopy}
              className="button-shell button-shell--secondary button-shell--sm gap-2 px-3"
            >
              <Copy className="h-3.5 w-3.5" />
              {translate("generated.executions.copiar_469807dc")}</button>
          )}
        </div>
      </div>
      {children}
    </div>
  );
}

function CodePanel({
  title,
  content,
  onCopy,
  mono = true,
  badge,
  variant,
  lang,
}: {
  title: string;
  content: string | null | undefined;
  onCopy?: () => void;
  mono?: boolean;
  badge?: ReactNode;
  variant: ExecutionDetailVariant;
  lang?: SyntaxLang;
}) {
  if (!content) {
    return null;
  }

  const isExpanded = variant === "expanded";
  const isPanel = variant === "panel";

  return (
    <div
      className={cn(
        "border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] shadow-none",
        isExpanded ? "rounded-lg p-5" : isPanel ? "rounded-lg p-4" : "rounded-lg p-4"
      )}
    >
      <div className="mb-3 flex items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
              {title}
            </span>
            {badge}
          </div>
        </div>
        {onCopy && (
          <button
            type="button"
            onClick={onCopy}
            className="button-shell button-shell--secondary button-shell--sm gap-2 px-3"
          >
            <Copy className="h-3.5 w-3.5" />
            {translate("common.copy")}
          </button>
        )}
      </div>
      {mono ? (
        <SyntaxHighlight
          lang={lang}
          className={cn(
            isExpanded
              ? "p-[18px] text-[13px]"
              : isPanel
                ? "p-3.5 text-[13px]"
                : "p-4 text-sm"
          )}
        >
          {content}
        </SyntaxHighlight>
      ) : (
        <pre
          className={cn(
            "overflow-x-auto whitespace-pre-wrap break-words border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] font-sans leading-7 text-[var(--text-secondary)]",
            isExpanded
              ? "rounded-lg p-[18px] text-[13px]"
              : isPanel
                ? "rounded-lg p-3.5 text-[13px]"
                : "rounded-lg p-4 text-sm"
          )}
        >
          {content}
        </pre>
      )}
    </div>
  );
}
