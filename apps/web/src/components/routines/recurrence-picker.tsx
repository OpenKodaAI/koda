"use client";

import { useMemo } from "react";
import { Input } from "@/components/ui/input";
import { SoftTabs } from "@/components/ui/soft-tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { StatusDot } from "@/components/ui/status-dot";
import { TimezonePicker } from "@/components/ui/timezone-picker";
import { DatePicker } from "@/components/routines/date-picker";
import { TimePicker } from "@/components/routines/time-picker";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  computeNextRuns,
  cronToPreset,
  validateCron,
  type RecurrenceFields,
  type RecurrencePreset,
} from "@/lib/routines/recurrence";
import { cn } from "@/lib/utils";

const WEEKDAYS = [
  "sunday",
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
] as const;

export interface RecurrencePickerValue {
  scheduleMode: "once" | "recurring";
  oneShotAt: string;
  recurrence: RecurrenceFields;
  customCron: string;
  timezone: string;
}

interface RecurrencePickerProps {
  value: RecurrencePickerValue;
  onChange: (next: RecurrencePickerValue) => void;
  disabled?: boolean;
}

const PRESETS: RecurrencePreset[] = ["hourly", "daily", "weekly", "monthly", "custom"];

function patch<T extends object>(value: T, partial: Partial<T>): T {
  return { ...value, ...partial };
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function parseOneShotAt(str: string): Date {
  if (!str) return new Date();
  const parsed = new Date(str);
  if (Number.isNaN(parsed.getTime())) return new Date();
  return parsed;
}

function formatOneShotAt(date: Date): string {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}T${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

function timeFromOneShot(str: string): string {
  const d = parseOneShotAt(str);
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

function applyTimeToOneShot(str: string, time: string): string {
  const d = parseOneShotAt(str);
  const match = /^(\d{1,2}):(\d{2})$/.exec(time);
  if (match) {
    d.setHours(Number(match[1]), Number(match[2]), 0, 0);
  }
  return formatOneShotAt(d);
}

function formatPreviewDate(date: Date, timezone: string, locale: string): string {
  try {
    return new Intl.DateTimeFormat(locale, {
      timeZone: timezone || undefined,
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  } catch {
    return date.toISOString().slice(0, 16).replace("T", " ");
  }
}

function formatRelative(date: Date, locale: string, now: Date = new Date()): string {
  const diffSec = Math.round((date.getTime() - now.getTime()) / 1000);
  const minutes = Math.round(diffSec / 60);
  const hours = Math.round(diffSec / 3600);
  const days = Math.round(diffSec / 86400);
  try {
    const formatter = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
    if (Math.abs(diffSec) < 60) return formatter.format(diffSec, "second");
    if (Math.abs(minutes) < 60) return formatter.format(minutes, "minute");
    if (Math.abs(hours) < 24) return formatter.format(hours, "hour");
    return formatter.format(days, "day");
  } catch {
    if (Math.abs(hours) < 24) return `${hours}h`;
    return `${days}d`;
  }
}

function humanizeRecurrence(
  fields: RecurrenceFields,
  t: ReturnType<typeof useAppI18n>["t"],
): string {
  if (fields.preset === "hourly") {
    return t("routines.editor.humanized.hourly");
  }
  if (fields.preset === "daily") {
    return t("routines.editor.humanized.daily", { time: fields.time });
  }
  if (fields.preset === "weekly") {
    const weekday = t(`routines.editor.weekdays.${WEEKDAYS[fields.weekday] ?? "monday"}`);
    return t("routines.editor.humanized.weekly", { weekday, time: fields.time });
  }
  if (fields.preset === "monthly") {
    return t("routines.editor.humanized.monthly", { day: fields.day, time: fields.time });
  }
  return "";
}

interface CronCellsProps {
  cron: string;
  onChange: (next: string) => void;
  disabled?: boolean;
  t: ReturnType<typeof useAppI18n>["t"];
}

function splitCron(cron: string): [string, string, string, string, string] {
  const fallback = "* * * * *";
  const segments = (cron && cron.trim() ? cron : fallback).trim().split(/\s+/);
  return [
    segments[0] ?? "*",
    segments[1] ?? "*",
    segments[2] ?? "*",
    segments[3] ?? "*",
    segments[4] ?? "*",
  ];
}

function CronCells({ cron, onChange, disabled, t }: CronCellsProps) {
  const [minute, hour, day, month, weekday] = splitCron(cron);
  const fields: Array<{ key: "minute" | "hour" | "day" | "month" | "weekday"; value: string; label: string }> = [
    { key: "minute", value: minute, label: t("routines.editor.cron.minute") },
    { key: "hour", value: hour, label: t("routines.editor.cron.hour") },
    { key: "day", value: day, label: t("routines.editor.cron.day") },
    { key: "month", value: month, label: t("routines.editor.cron.month") },
    { key: "weekday", value: weekday, label: t("routines.editor.cron.weekday") },
  ];

  function emit(updates: Partial<Record<typeof fields[number]["key"], string>>) {
    const next = {
      minute: updates.minute ?? minute,
      hour: updates.hour ?? hour,
      day: updates.day ?? day,
      month: updates.month ?? month,
      weekday: updates.weekday ?? weekday,
    };
    onChange(`${next.minute} ${next.hour} ${next.day} ${next.month} ${next.weekday}`);
  }

  return (
    <div className="grid grid-cols-5 gap-2">
      {fields.map((field) => (
        <label key={field.key} className="flex flex-col items-center gap-1.5">
          <input
            type="text"
            value={field.value}
            maxLength={1}
            onChange={(event) => {
              const raw = event.target.value;
              if (!raw) {
                emit({ [field.key]: "*" });
                return;
              }
              const last = raw.slice(-1);
              if (!/^[0-9*]$/.test(last)) return;
              emit({ [field.key]: last });
            }}
            onFocus={(event) => event.currentTarget.select()}
            disabled={disabled}
            inputMode="numeric"
            spellCheck={false}
            autoCapitalize="off"
            autoCorrect="off"
            placeholder="*"
            className={cn(
              "h-10 w-full rounded-[var(--radius-input)] border border-[var(--border-subtle)] bg-[var(--panel-soft)]",
              "text-center font-mono text-[0.9375rem] text-[var(--text-primary)] outline-none",
              "transition-[border-color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
              "placeholder:text-[var(--text-quaternary)]",
              "hover:border-[var(--border-strong)] focus-visible:border-[var(--accent)] focus-visible:bg-[var(--panel)]",
              "disabled:cursor-not-allowed disabled:opacity-60",
            )}
          />
          <span className="text-[0.6875rem] text-[var(--text-quaternary)]">{field.label}</span>
        </label>
      ))}
    </div>
  );
}

export function RecurrencePicker({ value, onChange, disabled = false }: RecurrencePickerProps) {
  const { t, i18n } = useAppI18n();
  const locale = i18n.language || "en-US";

  const detectedFromCustom = useMemo(() => {
    if (value.recurrence.preset !== "custom") return null;
    return cronToPreset(value.customCron || "");
  }, [value.recurrence.preset, value.customCron]);

  const cronError = useMemo(() => {
    if (value.recurrence.preset !== "custom") return null;
    if (!value.customCron) return null;
    return validateCron(value.customCron);
  }, [value.recurrence.preset, value.customCron]);

  const nextRuns = useMemo(() => {
    if (value.scheduleMode !== "recurring") return [];
    if (value.recurrence.preset === "custom") {
      if (cronError) return [];
      return detectedFromCustom ? computeNextRuns(detectedFromCustom, 3) : [];
    }
    return computeNextRuns(value.recurrence, 3);
  }, [value.scheduleMode, value.recurrence, detectedFromCustom, cronError]);

  return (
    <div className="flex flex-col gap-4">
      <SoftTabs
        items={[
          { id: "once", label: t("routines.editor.recurrence.once") },
          { id: "recurring", label: t("routines.editor.recurrence.recurring") },
        ]}
        value={value.scheduleMode}
        onChange={(id) => {
          if (disabled) return;
          onChange(patch(value, { scheduleMode: id as "once" | "recurring" }));
        }}
        ariaLabel={t("routines.editor.when")}
        className="self-start"
      />

      {value.scheduleMode === "once" ? (
        <div className="flex flex-col gap-3">
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,160px)]">
            <label className="flex flex-col gap-1.5">
              <span className="text-[0.75rem] font-medium text-[var(--text-tertiary)]">
                {t("routines.editor.date")}
              </span>
              <DatePicker
                value={parseOneShotAt(value.oneShotAt)}
                onChange={(date) => onChange(patch(value, { oneShotAt: formatOneShotAt(date) }))}
                disabled={disabled}
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-[0.75rem] font-medium text-[var(--text-tertiary)]">
                {t("routines.editor.timeOfDay")}
              </span>
              <TimePicker
                value={timeFromOneShot(value.oneShotAt)}
                onChange={(time) =>
                  onChange(patch(value, { oneShotAt: applyTimeToOneShot(value.oneShotAt, time) }))
                }
                disabled={disabled}
              />
            </label>
          </div>
          <label className="flex flex-col gap-1.5">
            <span className="text-[0.75rem] font-medium text-[var(--text-tertiary)]">
              {t("routines.editor.timezone")}
            </span>
            <TimezonePicker
              value={value.timezone}
              onValueChange={(tz) => onChange(patch(value, { timezone: tz }))}
              disabled={disabled}
            />
          </label>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <SoftTabs
            items={PRESETS.map((preset) => ({
              id: preset,
              label: t(`routines.editor.presets.${preset}`),
            }))}
            value={value.recurrence.preset}
            onChange={(id) => {
              if (disabled) return;
              onChange(
                patch(value, {
                  recurrence: patch(value.recurrence, { preset: id as RecurrencePreset }),
                }),
              );
            }}
            ariaLabel={t("routines.editor.presetsLabel")}
            className="self-start"
          />

          {value.recurrence.preset !== "hourly" && value.recurrence.preset !== "custom" ? (
            <div className="grid gap-3 md:grid-cols-2">
              <label className="flex flex-col gap-1.5">
                <span className="text-[0.75rem] font-medium text-[var(--text-tertiary)]">
                  {t("routines.editor.timeOfDay")}
                </span>
                <TimePicker
                  value={value.recurrence.time}
                  onChange={(time) =>
                    onChange(
                      patch(value, {
                        recurrence: patch(value.recurrence, { time }),
                      }),
                    )
                  }
                  disabled={disabled}
                />
              </label>

              {value.recurrence.preset === "weekly" ? (
                <label className="flex flex-col gap-1.5">
                  <span className="text-[0.75rem] font-medium text-[var(--text-tertiary)]">
                    {t("routines.editor.weekday")}
                  </span>
                  <Select
                    value={String(value.recurrence.weekday)}
                    onValueChange={(v) =>
                      onChange(
                        patch(value, {
                          recurrence: patch(value.recurrence, { weekday: Number(v) }),
                        }),
                      )
                    }
                    disabled={disabled}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {WEEKDAYS.map((day, index) => (
                        <SelectItem key={day} value={String(index)}>
                          {t(`routines.editor.weekdays.${day}`)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </label>
              ) : null}

              {value.recurrence.preset === "monthly" ? (
                <label className="flex flex-col gap-1.5">
                  <span className="text-[0.75rem] font-medium text-[var(--text-tertiary)]">
                    {t("routines.editor.dayOfMonth")}
                  </span>
                  <Input
                    type="number"
                    min={1}
                    max={28}
                    value={value.recurrence.day}
                    onChange={(event) => {
                      const parsed = Number(event.target.value);
                      const day = Number.isFinite(parsed) ? parsed : 1;
                      onChange(
                        patch(value, {
                          recurrence: patch(value.recurrence, { day }),
                        }),
                      );
                    }}
                    disabled={disabled}
                  />
                </label>
              ) : null}
            </div>
          ) : null}

          {value.recurrence.preset === "custom" ? (
            <div className="flex flex-col gap-2">
              <span className="text-[0.75rem] font-medium text-[var(--text-tertiary)]">
                {t("routines.editor.customCron")}
              </span>
              <CronCells
                cron={value.customCron}
                onChange={(next) => onChange(patch(value, { customCron: next }))}
                disabled={disabled}
                t={t}
              />
              <span
                className={cn(
                  "min-h-[1.05rem] text-[0.8125rem] transition-colors duration-[120ms]",
                  cronError
                    ? "text-[var(--tone-danger-text)]"
                    : detectedFromCustom
                      ? "text-[var(--text-secondary)]"
                      : "text-[var(--text-quaternary)]",
                )}
              >
                {cronError
                  ? t(`routines.editor.cronErrors.${cronError.code}`, {
                      cell: t(`routines.editor.cron.${cronError.cell}`),
                    })
                  : detectedFromCustom
                    ? humanizeRecurrence(detectedFromCustom, t)
                    : t("routines.editor.customCronHint")}
              </span>
            </div>
          ) : null}

          <label className="flex flex-col gap-1.5">
            <span className="text-[0.75rem] font-medium text-[var(--text-tertiary)]">
              {t("routines.editor.timezone")}
            </span>
            <TimezonePicker
              value={value.timezone}
              onValueChange={(tz) => onChange(patch(value, { timezone: tz }))}
              disabled={disabled}
            />
          </label>

          {nextRuns.length > 0 ? (
            <div className="flex flex-col gap-2">
              <span className="font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
                {t("routines.editor.nextRuns")}
              </span>
              <ol className="m-0 flex flex-col p-0">
                {nextRuns.map((run) => (
                  <li
                    key={run.toISOString()}
                    className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 border-b border-[color:var(--divider-hair)] py-2 last:border-b-0"
                  >
                    <StatusDot tone="info" />
                    <span className="font-mono text-[0.8125rem] text-[var(--text-secondary)]">
                      {formatPreviewDate(run, value.timezone, locale)}
                    </span>
                    <span className="text-[0.75rem] text-[var(--text-quaternary)]">
                      {formatRelative(run, locale)}
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          ) : value.recurrence.preset === "custom" ? null : (
            <span className="text-[0.8125rem] text-[var(--text-tertiary)]">
              {t("routines.editor.nextRunsUnavailable")}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
