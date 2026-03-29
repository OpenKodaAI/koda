"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Copy,
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
  getSemanticDotStyle,
  getSemanticIconStyle,
  getSemanticStrongStyle,
  getSemanticStyle,
  getSemanticTextStyle,
  type SemanticTone,
} from "@/lib/theme-semantic";
import { DetailRow } from "../shared/detail-row";
import { DetailsViewer } from "../audit/details-viewer";
import { SyntaxHighlight, type SyntaxLang } from "../shared/syntax-highlight";
import { translate, translateLiteral } from "@/lib/i18n";

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
      className="inline-flex rounded-lg border px-2.5 py-1 text-[10px] font-semibold tracking-[0.04em]"
      style={getSemanticStyle(meta.tone)}
    >
      {translate(meta.labelKey)}
    </span>
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
    <div className="metric-strip">
      <ExecutionMetric label={translate("common.cost")} value={formatCost(data.cost_usd)} mono />
      <ExecutionMetric label={translate("common.duration")} value={formatDuration(data.duration_ms)} mono />
      <ExecutionMetric label={translate("common.attempts")} value={`${data.attempt}/${data.max_attempts}`} mono />
      <ExecutionMetric label={translate("common.tools")} value={String(data.tool_count)} mono />
      <ExecutionMetric label={translate("common.warnings")} value={String(data.warnings.length)} mono />
    </div>
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
    </>
  );

  const summarySection = (
    <DetailSection
      title={translate("executions.detail.signals")}
      variant={variant}
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <DetailRow label={translate("executions.detail.traceSource")}>
          <ExecutionSourceBadge meta={traceSource} />
        </DetailRow>
        <DetailRow label={translate("executions.detail.responseSource")}>
          <ExecutionSourceBadge meta={responseSource} />
        </DetailRow>
        <DetailRow label={translate("executions.detail.toolsSource")}>
          <ExecutionSourceBadge meta={toolsSource} />
        </DetailRow>
        <DetailRow label={translate("executions.detail.stopReason")}>
          <span className="font-mono">{data.stop_reason ?? translate("executions.detail.notProvided")}</span>
        </DetailRow>
        <DetailRow label={translate("common.createdAt", { defaultValue: translateLiteral("Criada em") })}>
          {formatDateTime(data.created_at)}
        </DetailRow>
        <DetailRow label={translate("common.startedAt")}>{formatDateTime(data.started_at)}</DetailRow>
        <DetailRow label={translate("common.completedAt")}>{formatDateTime(data.completed_at)}</DetailRow>
        <DetailRow label={translate("common.totalTime")}>
          <span className="font-mono">{formatDuration(data.duration_ms)}</span>
        </DetailRow>
        <DetailRow label={translate("executions.detail.runtime")}>
          <Link
            href={`/runtime/${data.bot_id}/tasks/${data.task_id}`}
            className="button-pill is-active"
          >
            {translate("executions.detail.openRuntimeRoom")}
          </Link>
        </DetailRow>
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
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <DetailRow label={translate("common.model")}>
          <span className="font-mono">{data.model ?? "—"}</span>
        </DetailRow>
        <DetailRow label={translate("common.session")}>
          <span className="break-all font-mono text-xs">{data.session_id ?? "—"}</span>
        </DetailRow>
        <DetailRow label={translate("common.workspaceDirectory")}>
          <span className="break-all font-mono text-xs">{data.work_dir ?? "—"}</span>
        </DetailRow>
        <DetailRow label={translateLiteral("User / chat")}>
          <span className="font-mono">
            {data.user_id} / {data.chat_id}
          </span>
        </DetailRow>
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
              "border border-[var(--border-subtle)] bg-[var(--field-bg)] text-sm leading-6 text-[var(--text-secondary)] shadow-[inset_0_1px_0_rgba(231,235,240,0.012)]",
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
        {notices}
        {summarySection}
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
    <div className="space-y-8">
      {metrics}
      <div className="grid gap-7 xl:grid-cols-[minmax(0,1.55fr)_360px]">
        <div className="space-y-7">
          {entrySection}
          {responseSection}
          {toolsSection}
          {artifactsSection}
        </div>
        <div className="space-y-7">
          {notices}
          {summarySection}
          {timelineSection}
          {reasoningSection}
        </div>
      </div>
    </div>
  );
}

function DetailSection({
  title,
  variant,
  children,
}: {
  title: string;
  variant: ExecutionDetailVariant;
  children: ReactNode;
}) {
  const isExpanded = variant === "expanded";
  return (
    <section className={cn("space-y-3.5", isExpanded && "space-y-4")}>
      <div className="section-label">
        <span>{title}</span>
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
        isExpanded ? "rounded-lg p-5" : isPanel ? "rounded-lg p-4" : "rounded-lg p-4"
      )}
      style={getSemanticStyle("warning")}
    >
      <div className="mb-3 flex items-start justify-between gap-4">
        <div>
          <span className="text-[10px] font-semibold uppercase tracking-[0.14em]" style={getSemanticTextStyle("warning")}>
            {translate("common.warnings")}
          </span>
        </div>
        <span className="rounded-lg border px-3 py-1 text-[11px] font-semibold" style={getSemanticStrongStyle("warning")}>
          {warnings.length}
        </span>
      </div>
      <div className="space-y-2">
        {warnings.map((warning, index) => (
          <div
            key={`${warning}-${index}`}
            className={cn(
              "border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.02)] text-sm leading-6",
              isExpanded ? "rounded-lg px-4 py-3.5" : isPanel ? "rounded-lg px-4 py-3" : "rounded-lg px-4 py-3"
            )}
            style={getSemanticStyle("warning")}
          >
            {warning}
          </div>
        ))}
      </div>
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
  const tone = TIMELINE_TONE[item.status];
  const isExpanded = variant === "expanded";
  const isPanel = variant === "panel";

  return (
    <div
      className={cn(
        "border shadow-none",
        isExpanded ? "rounded-lg p-5" : isPanel ? "rounded-lg p-4" : "rounded-lg p-4"
      )}
      style={getSemanticStyle(tone)}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex items-center gap-3">
            <span className="h-2.5 w-2.5 rounded-full" style={getSemanticDotStyle(tone)} />
            <p className="text-sm font-semibold text-[var(--text-primary)]">{item.title}</p>
          </div>
          {item.summary && (
            <p className="text-[13px] leading-6 text-[var(--text-secondary)]">{item.summary}</p>
          )}
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-tertiary)]">
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
        "border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.012)] shadow-none",
        isExpanded ? "rounded-lg p-5" : isPanel ? "rounded-lg p-4" : "rounded-lg p-4"
      )}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[var(--text-primary)]">{tool.tool}</p>
            <p className="text-[13px] leading-6 text-[var(--text-secondary)]">{tool.summary}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-tertiary)]">
            <span className="rounded-lg border border-[var(--border-subtle)] bg-[var(--field-bg)] px-2.5 py-1 font-mono text-[10px] text-[var(--text-secondary)]">
              {tool.category}
            </span>
            <span
              className="rounded-lg border px-2.5 py-1 text-[10px] font-semibold"
              style={getSemanticStyle(tool.success === false ? "danger" : "success")}
            >
              {tool.success === false
                ? translate("common.failed", { defaultValue: "Failed" })
                : translate("toast.success", { defaultValue: "Success" })}
            </span>
            <span className="font-mono">{formatDuration(tool.duration_ms)}</span>
            <span>{formatDateTime(tool.completed_at ?? tool.started_at)}</span>
            {tool.redactions && (
              <span className="rounded-lg border px-2.5 py-1 text-[10px] font-semibold" style={getSemanticStyle("warning")}>
                {translate("executions.detail.redactions", {
                  defaultValue: "{{count}} redactions",
                  count: tool.redactions.count,
                })}
              </span>
            )}
          </div>
        </div>
        {tool.output && (
          <button
            type="button"
            onClick={() => copyExecutionValue(tool.output)}
            className="button-shell button-shell--secondary button-shell--sm gap-2 px-3"
          >
            <Copy className="h-3.5 w-3.5" />
            {translateLiteral("Copiar saída")}
          </button>
        )}
      </div>

      <div
        className={cn(
          "mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2",
          isExpanded ? "lg:grid-cols-4" : isPanel ? "xl:grid-cols-2" : isDrawer && "md:grid-cols-2"
        )}
      >
        <DetailRow label={translateLiteral("Início")}>{formatDateTime(tool.started_at)}</DetailRow>
        <DetailRow label={translateLiteral("Fim")}>{formatDateTime(tool.completed_at)}</DetailRow>
        <DetailRow label={translate("common.duration")}>
          <span className="font-mono">{formatDuration(tool.duration_ms)}</span>
        </DetailRow>
        <DetailRow label={translateLiteral("Categoria")}>
          <span className="font-mono">{tool.category}</span>
        </DetailRow>
      </div>

      {command && (
        <div className="mt-4">
          <CodePanel
            title={binary || args ? translateLiteral("Comando CLI") : translate("common.command", { defaultValue: "Command" })}
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
            title={translateLiteral("Consulta SQL")}
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
        {env && <DetailRow label={translateLiteral("Ambiente")}>{env}</DetailRow>}
        {maxRows != null && <DetailRow label={translateLiteral("Limite de linhas")}>{String(maxRows)}</DetailRow>}
        {analyze != null && <DetailRow label={translateLiteral("Analyze")}>{analyze ? translateLiteral("Sim") : translateLiteral("Não")}</DetailRow>}
        {exitCode != null && (
          <DetailRow label={translateLiteral("Código de saída")}>
            <span className="font-mono">{String(exitCode)}</span>
          </DetailRow>
        )}
        {timedOut != null && <DetailRow label={translateLiteral("Timeout")}>{timedOut ? translateLiteral("Sim") : translateLiteral("Não")}</DetailRow>}
        {truncated != null && <DetailRow label={translateLiteral("Saída truncada")}>{truncated ? translateLiteral("Sim") : translateLiteral("Não")}</DetailRow>}
      </div>

      {hasEntries(tool.params) && (
        <div className="mt-4">
          <ArtifactShell
            title={translateLiteral("Parâmetros enviados")}
            onCopy={() => copyExecutionValue(tool.params)}
            variant={variant}
          >
            <DetailsViewer data={tool.params} />
          </ArtifactShell>
        </div>
      )}

      {tool.output && (
        <div className="mt-4">
          <CodePanel
            title={translateLiteral("Saída da ferramenta")}
            content={tool.output}
            onCopy={() => copyExecutionValue(tool.output)}
            variant={variant}
          />
        </div>
      )}

      {hasEntries(extraMetadata) && (
        <div className="mt-4">
          <ArtifactShell
            title={translateLiteral("Metadados adicionais")}
            onCopy={() => copyExecutionValue(extraMetadata)}
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

  return (
    <ArtifactShell
      title={artifact.label}
      onCopy={() => copyExecutionValue(artifact.content)}
      unavailable={artifact.unavailable}
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
  variant,
}: {
  title: string;
  children: ReactNode;
  onCopy?: () => void;
  unavailable?: boolean;
  variant: ExecutionDetailVariant;
}) {
  const isExpanded = variant === "expanded";
  const isPanel = variant === "panel";

  return (
    <div
      className={cn(
        "border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.012)] shadow-none",
        isExpanded ? "rounded-lg p-5" : isPanel ? "rounded-lg p-4" : "rounded-lg p-4"
      )}
    >
      <div className="mb-3 flex items-start justify-between gap-4">
        <div>
          <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
            {title}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {unavailable && (
            <span className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-2.5 py-1 text-[10px] font-semibold text-[var(--text-tertiary)]">
              {translateLiteral("Indisponível")}
            </span>
          )}
          {onCopy && (
            <button
              type="button"
              onClick={onCopy}
              className="button-shell button-shell--secondary button-shell--sm gap-2 px-3"
            >
              <Copy className="h-3.5 w-3.5" />
              Copiar
            </button>
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
        "border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.012)] shadow-none",
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
            "overflow-x-auto whitespace-pre-wrap break-words border border-[rgba(255,255,255,0.06)] bg-[rgba(10,10,10,0.84)] font-sans leading-7 text-[var(--text-secondary)]",
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

function ExecutionMetric({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
  variant?: ExecutionDetailVariant;
}) {
  return (
    <div className="metric-strip__item">
      <span className="metric-label">{label}</span>
      <span className={cn("text-[var(--text-primary)] text-base", mono && "font-mono tabular-nums")}>
        {value}
      </span>
    </div>
  );
}
