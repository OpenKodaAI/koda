"use client";

import { useCallback, useMemo, useState } from "react";
import { AlertTriangle, Check, MessageSquareReply, PencilLine, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { InlineAlert } from "@/components/ui/inline-alert";
import { JsonEditor, type JsonValidation } from "@/components/ui/json-editor";
import { StatusDot } from "@/components/ui/status-dot";
import { Textarea } from "@/components/ui/textarea";
import { useApprovalAction } from "@/hooks/use-approval-action";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type { ApprovalDecision, ApprovalParams } from "@/lib/contracts/sessions";
import { cn } from "@/lib/utils";

interface ApprovalPromptProps {
  agentId: string;
  sessionId: string;
  approvalId: string;
  toolName?: string | null;
  reasons?: string[];
  preview?: string | null;
  schema?: Record<string, unknown> | null;
  toolSchema?: Record<string, unknown> | null;
  inputSchema?: Record<string, unknown> | null;
  params?: ApprovalParams | null;
  originalParams?: ApprovalParams | null;
  onResolved?: (decision: ApprovalDecision) => void;
}

type DiffRow = {
  kind: "same" | "remove" | "add";
  text: string;
};

const MAX_DIFF_ROWS = 80;

function stringifyJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

function isJsonObject(value: unknown): value is ApprovalParams {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function parseJsonObject(raw: string):
  | { ok: true; value: ApprovalParams }
  | { ok: false; error: string } {
  const source = raw.trim() || "{}";
  try {
    const parsed = JSON.parse(source);
    if (!isJsonObject(parsed)) {
      return { ok: false, error: "Edited parameters must be a JSON object." };
    }
    return { ok: true, value: parsed };
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : "Edited parameters are not valid JSON.",
    };
  }
}

function formatJsonValidation(status: JsonValidation): string | null {
  if (status.valid) return null;
  if (status.line && status.column) {
    return `${status.error ?? "Invalid JSON"} at line ${status.line}, column ${status.column}.`;
  }
  return status.error ?? "Invalid JSON.";
}

function normalizedEditedJson(raw: string): string {
  const parsed = parseJsonObject(raw);
  return parsed.ok ? stringifyJson(parsed.value) : raw.trim();
}

function buildJsonDiffRows(before: string, after: string): DiffRow[] {
  if (before === after) return [];

  const beforeLines = before.split("\n");
  const afterLines = after.split("\n");
  const table = Array.from({ length: beforeLines.length + 1 }, () =>
    Array<number>(afterLines.length + 1).fill(0),
  );

  for (let i = beforeLines.length - 1; i >= 0; i -= 1) {
    for (let j = afterLines.length - 1; j >= 0; j -= 1) {
      table[i]![j] =
        beforeLines[i] === afterLines[j]
          ? table[i + 1]![j + 1]! + 1
          : Math.max(table[i + 1]![j]!, table[i]![j + 1]!);
    }
  }

  const rows: DiffRow[] = [];
  let i = 0;
  let j = 0;
  while (i < beforeLines.length && j < afterLines.length) {
    if (beforeLines[i] === afterLines[j]) {
      rows.push({ kind: "same", text: beforeLines[i]! });
      i += 1;
      j += 1;
    } else if (table[i + 1]![j]! >= table[i]![j + 1]!) {
      rows.push({ kind: "remove", text: beforeLines[i]! });
      i += 1;
    } else {
      rows.push({ kind: "add", text: afterLines[j]! });
      j += 1;
    }
  }

  while (i < beforeLines.length) {
    rows.push({ kind: "remove", text: beforeLines[i]! });
    i += 1;
  }
  while (j < afterLines.length) {
    rows.push({ kind: "add", text: afterLines[j]! });
    j += 1;
  }

  return rows;
}

export function ApprovalPrompt({
  agentId,
  sessionId,
  approvalId,
  toolName,
  reasons,
  preview,
  schema,
  toolSchema,
  inputSchema,
  params,
  originalParams,
  onResolved,
}: ApprovalPromptProps) {
  const { t } = useAppI18n();
  const { submit, isPending, error } = useApprovalAction({ agentId, sessionId });
  const [rationale, setRationale] = useState("");
  const [responseText, setResponseText] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [jsonValidationError, setJsonValidationError] = useState<string | null>(null);

  const effectiveSchema = schema ?? toolSchema ?? inputSchema ?? null;
  const effectiveOriginalParams = originalParams ?? params ?? null;
  const hasParamEditor = Boolean(effectiveSchema || effectiveOriginalParams);
  const originalParamsText = useMemo(
    () => stringifyJson(effectiveOriginalParams ?? {}),
    [effectiveOriginalParams],
  );
  const [editedParamsText, setEditedParamsText] = useState(originalParamsText);

  const editedParamsDiffText = useMemo(
    () => normalizedEditedJson(editedParamsText),
    [editedParamsText],
  );
  const diffRows = useMemo(
    () =>
      hasParamEditor
        ? buildJsonDiffRows(originalParamsText, editedParamsDiffText)
        : [],
    [editedParamsDiffText, hasParamEditor, originalParamsText],
  );
  const visibleDiffRows = diffRows.slice(0, MAX_DIFF_ROWS);
  const hiddenDiffCount = Math.max(diffRows.length - visibleDiffRows.length, 0);

  const handleJsonValidate = useCallback((status: JsonValidation) => {
    setJsonValidationError(formatJsonValidation(status));
  }, []);

  async function resolve(
    decision: ApprovalDecision,
    options: { editedParams?: ApprovalParams | null; responseText?: string | null } = {},
  ) {
    setLocalError(null);
    const result = await submit({
      approvalId,
      decision,
      editedParams: options.editedParams ?? null,
      responseText: options.responseText ?? null,
      rationale: rationale.trim() || null,
    });
    if (result) {
      onResolved?.(decision);
    }
  }

  async function handleReject() {
    await resolve("reject");
  }

  async function handleRespond() {
    const trimmedResponse = responseText.trim();
    if (!trimmedResponse) {
      setLocalError(t("generated.sessions.add_response_text_before_responding_e7f533b5"));
      return;
    }
    await resolve("respond", { responseText: trimmedResponse });
  }

  async function handleEdit() {
    if (!hasParamEditor) {
      setLocalError(t("generated.sessions.no_editable_parameters_were_provided_for_thi_d12e9209"));
      return;
    }
    if (jsonValidationError) {
      setLocalError(t("generated.sessions.fix_invalid_json_before_submitting_edited_pa_484a6a78"));
      return;
    }
    const parsed = parseJsonObject(editedParamsText);
    if (!parsed.ok) {
      setLocalError(parsed.error);
      return;
    }
    if (stringifyJson(parsed.value) === originalParamsText) {
      setLocalError(t("generated.sessions.change_at_least_one_parameter_or_approve_wit_f96e39d7"));
      return;
    }
    await resolve("edit", { editedParams: parsed.value });
  }

  async function handleApprove() {
    await resolve("approve");
  }

  const displayedError = localError ?? (error ? `${error}. ${t("generated.sessions.review_the_approval_details_and_try_again_01e00519")}` : null);

  return (
    <div className="mt-2 flex flex-col gap-3 rounded-[var(--radius-panel)] border border-[color:var(--tone-warning-border)] bg-[color:var(--tone-warning-bg)] px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <StatusDot tone="warning" pulse />
        <span className="text-[var(--font-size-sm)] font-medium text-[var(--tone-warning-text)]">
          {t("generated.sessions.approval_required_c1a6f49c")}
        </span>
        {toolName ? (
          <span className="truncate font-mono text-[12px] text-[var(--text-tertiary)]">
            {toolName}
          </span>
        ) : null}
      </div>

      {reasons && reasons.length > 0 ? (
        <ul className="m-0 list-disc space-y-1 pl-5 text-[var(--font-size-sm)] text-[var(--text-secondary)]">
          {reasons.map((reason, index) => (
            <li key={index}>{reason}</li>
          ))}
        </ul>
      ) : null}

      {preview ? (
        <pre className="m-0 max-h-40 overflow-auto whitespace-pre-wrap rounded-[var(--radius-chip)] bg-[var(--panel-strong)] px-3 py-2 font-mono text-[12px] text-[var(--text-secondary)]">
          {preview}
        </pre>
      ) : null}

      {hasParamEditor ? (
        <section className="flex flex-col gap-2 rounded-[var(--radius-panel-sm)] border border-[color:var(--divider-hair)] bg-[var(--panel-soft)] p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
              {t("generated.sessions.parameters_bb95e589")}
            </span>
            {effectiveSchema ? (
              <span className="rounded-[var(--radius-chip)] bg-[var(--tone-info-bg)] px-2 py-0.5 text-[11px] text-[var(--tone-info-text)]">
                {t("generated.sessions.schema_available_b3403497")}
              </span>
            ) : null}
          </div>

          <JsonEditor
            value={editedParamsText}
            onChange={(next) => {
              setEditedParamsText(next);
              setLocalError(null);
            }}
            onValidate={handleJsonValidate}
            rows={6}
            ariaLabel={t("generated.sessions.edited_parameters_json_422e304d")}
            readOnly={isPending}
          />

          {effectiveSchema ? (
            <details className="rounded-[var(--radius-chip)] border border-[color:var(--divider-hair)] bg-[var(--panel)] px-3 py-2">
              <summary className="cursor-pointer text-[12px] text-[var(--text-tertiary)]">
                {t("generated.sessions.schema_d57f85f4")}
              </summary>
              <pre className="m-0 mt-2 max-h-32 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-[var(--text-secondary)]">
                {stringifyJson(effectiveSchema)}
              </pre>
            </details>
          ) : null}

          <div
            aria-label={t("generated.sessions.parameter_diff_55849f7f")}
            className="rounded-[var(--radius-chip)] border border-[color:var(--divider-hair)] bg-[var(--panel)]"
          >
            <div className="border-b border-[color:var(--divider-hair)] px-3 py-2 font-mono text-[11px] uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
              {t("generated.sessions.parameter_diff_55849f7f")}
            </div>
            {diffRows.length === 0 ? (
              <p className="m-0 px-3 py-2 text-[12px] text-[var(--text-tertiary)]">
                {t("generated.sessions.no_parameter_changes_c0f8c6a2")}
              </p>
            ) : (
              <pre className="m-0 max-h-40 overflow-auto py-1 font-mono text-[11px] leading-[1.45]">
                {visibleDiffRows.map((row, index) => {
                  const prefix =
                    row.kind === "add" ? "+" : row.kind === "remove" ? "-" : " ";
                  return (
                    <code
                      key={`${row.kind}-${index}`}
                      className={cn(
                        "block whitespace-pre-wrap break-words px-3 py-0.5",
                        row.kind === "add" &&
                          "bg-[var(--tone-success-bg)] text-[var(--tone-success-text)]",
                        row.kind === "remove" &&
                          "bg-[var(--tone-danger-bg)] text-[var(--tone-danger-text)]",
                        row.kind === "same" && "text-[var(--text-tertiary)]",
                      )}
                    >
                      {`${prefix} ${row.text}`}
                    </code>
                  );
                })}
                {hiddenDiffCount > 0 ? (
                  <code className="block px-3 py-1 text-[var(--text-quaternary)]">
                    {`... ${hiddenDiffCount} more lines`}
                  </code>
                ) : null}
              </pre>
            )}
          </div>
        </section>
      ) : null}

      <div className="grid gap-2 sm:grid-cols-2">
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
            {t("generated.sessions.rationale_b8450b4b")}
          </span>
          <Textarea
            className="min-h-[56px] resize-none"
            placeholder={t("generated.sessions.optional_rationale_5afe0d45")}
            rows={2}
            maxLength={500}
            value={rationale}
            onChange={(event) => setRationale(event.target.value)}
            disabled={isPending}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
            {t("generated.sessions.response_5b0d921c")}
          </span>
          <Textarea
            className="min-h-[56px] resize-none"
            placeholder={t("generated.sessions.response_text_for_respond_1cec3c25")}
            rows={2}
            maxLength={10_000}
            value={responseText}
            onChange={(event) => {
              setResponseText(event.target.value);
              setLocalError(null);
            }}
            disabled={isPending}
          />
        </label>
      </div>

      {displayedError ? (
        <InlineAlert tone="danger" className="py-2">
          {displayedError}
        </InlineAlert>
      ) : null}

      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button
          variant="destructive"
          size="sm"
          disabled={isPending}
          onClick={handleReject}
        >
          <X strokeWidth={1.75} className="icon-sm" />
          {t("generated.sessions.reject_d546cfdf")}
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={isPending}
          onClick={handleRespond}
        >
          <MessageSquareReply strokeWidth={1.75} className="icon-sm" />
          {t("generated.sessions.respond_c3a6b1f7")}
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={isPending}
          onClick={handleEdit}
        >
          <PencilLine strokeWidth={1.75} className="icon-sm" />
          {t("generated.sessions.edit_ad5e46b8")}
        </Button>
        <Button
          variant="accent"
          size="sm"
          disabled={isPending}
          onClick={handleApprove}
        >
          <Check strokeWidth={1.75} className="icon-sm" />
          {t("generated.sessions.approve_9b47d928")}
        </Button>
      </div>
      <p className="m-0 flex items-center gap-1 text-[11px] text-[var(--text-tertiary)]">
        <AlertTriangle strokeWidth={1.5} className="icon-xs" />
        {t("generated.sessions.runtime_pauses_until_you_answer_0c0a64a4")}
      </p>
    </div>
  );
}
