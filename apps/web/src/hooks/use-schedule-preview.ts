"use client";

import { useEffect, useState } from "react";
import { scheduleErrorMessage } from "@/lib/contracts/schedules";

export interface SchedulePreviewRequest {
  agentId: string;
  triggerType: "cron" | "interval";
  scheduleExpr: string;
  timezone: string;
}

/**
 * `invalid` means the scheduler rejected the schedule (its reason is in `message`);
 * `unavailable` means the preview could not be fetched, which does not block saving.
 */
export interface SchedulePreview {
  status: "idle" | "loading" | "ready" | "invalid" | "unavailable";
  nextRuns: Date[];
  message: string | null;
}

const IDLE: SchedulePreview = { status: "idle", nextRuns: [], message: null };
const LOADING: SchedulePreview = { status: "loading", nextRuns: [], message: null };
const DEBOUNCE_MS = 250;

function previewFromResponse(status: number, body: unknown): SchedulePreview {
  if (status >= 200 && status < 300) {
    const runs = (body as { next_runs?: unknown } | null)?.next_runs;
    const nextRuns = (Array.isArray(runs) ? runs : [])
      .map((run) => new Date(String(run)))
      .filter((run) => !Number.isNaN(run.getTime()));
    return { status: "ready", nextRuns, message: null };
  }
  if (status === 422) {
    return { status: "invalid", nextRuns: [], message: scheduleErrorMessage(body, "") || null };
  }
  return { status: "unavailable", nextRuns: [], message: null };
}

/**
 * Asks the scheduler to validate a recurring schedule and list its next runs (D-080, D-081),
 * so the editor accepts what the scheduler accepts and previews what it will run.
 */
export function useSchedulePreview(request: SchedulePreviewRequest | null): SchedulePreview {
  const key = request
    ? JSON.stringify([request.agentId, request.triggerType, request.scheduleExpr, request.timezone])
    : null;
  const [result, setResult] = useState<{ key: string; preview: SchedulePreview } | null>(null);

  useEffect(() => {
    if (!key) return;
    const [agentId, triggerType, scheduleExpr, timezone] = JSON.parse(key) as string[];
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      const search = new URLSearchParams({
        trigger_type: triggerType,
        schedule_expr: scheduleExpr,
        timezone,
      });
      let preview: SchedulePreview;
      try {
        const response = await fetch(
          `/api/runtime/agents/${encodeURIComponent(agentId)}/schedules/preview?${search}`,
          { cache: "no-store", signal: controller.signal },
        );
        preview = previewFromResponse(response.status, await response.json().catch(() => null));
      } catch {
        preview = { status: "unavailable", nextRuns: [], message: null };
      }
      if (!controller.signal.aborted) setResult({ key, preview });
    }, DEBOUNCE_MS);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [key]);

  if (!key) return IDLE;
  return result?.key === key ? result.preview : LOADING;
}
