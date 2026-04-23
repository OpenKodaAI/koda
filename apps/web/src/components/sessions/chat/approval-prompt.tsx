"use client";

import { useState } from "react";
import { AlertTriangle, Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusDot } from "@/components/ui/status-dot";
import { useApprovalAction } from "@/hooks/use-approval-action";
import type { ApprovalDecision } from "@/lib/contracts/sessions";

interface ApprovalPromptProps {
  agentId: string;
  sessionId: string;
  approvalId: string;
  toolName?: string | null;
  reasons?: string[];
  preview?: string | null;
  onResolved?: (decision: ApprovalDecision) => void;
}

export function ApprovalPrompt({
  agentId,
  sessionId,
  approvalId,
  toolName,
  reasons,
  preview,
  onResolved,
}: ApprovalPromptProps) {
  const { submit, isPending, error } = useApprovalAction({ agentId, sessionId });
  const [rationale, setRationale] = useState("");

  async function handle(decision: ApprovalDecision) {
    const result = await submit({
      approvalId,
      decision,
      rationale: rationale.trim() || null,
    });
    if (result) {
      onResolved?.(decision);
    }
  }

  return (
    <div className="mt-2 flex flex-col gap-3 rounded-[var(--radius-panel)] border border-[color:var(--tone-warning-border)] bg-[color:var(--tone-warning-bg)] px-4 py-3">
      <div className="flex items-center gap-2">
        <StatusDot tone="warning" pulse />
        <span className="text-[var(--font-size-sm)] font-medium text-[var(--tone-warning-text)]">
          Approval required
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

      <textarea
        className="min-h-[36px] w-full resize-none rounded-[var(--radius-input)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] px-3 py-2 text-[var(--font-size-sm)] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:outline-none focus:ring-1 focus:ring-[color:var(--accent-muted)]"
        placeholder="Optional rationale"
        rows={2}
        maxLength={500}
        value={rationale}
        onChange={(event) => setRationale(event.target.value)}
        disabled={isPending}
      />

      {error ? (
        <p className="m-0 text-[var(--font-size-sm)] text-[var(--tone-danger-text)]">
          {error}
        </p>
      ) : null}

      <div className="flex items-center justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={isPending}
          onClick={() => handle("deny")}
        >
          <X strokeWidth={1.75} className="icon-sm" />
          Deny
        </Button>
        <Button
          variant="accent"
          size="sm"
          disabled={isPending}
          onClick={() => handle("approve")}
        >
          <Check strokeWidth={1.75} className="icon-sm" />
          Approve
        </Button>
      </div>
      <p className="m-0 flex items-center gap-1 text-[11px] text-[var(--text-tertiary)]">
        <AlertTriangle strokeWidth={1.5} className="icon-xs" />
        Runtime pauses until you answer.
      </p>
    </div>
  );
}
