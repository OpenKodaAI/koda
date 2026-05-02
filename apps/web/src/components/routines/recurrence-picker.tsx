"use client";

import { useMemo } from "react";
import {
  Input,
} from "@/components/ui/input";
import { SoftTabs } from "@/components/ui/soft-tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { TimezonePicker } from "@/components/ui/timezone-picker";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  computeNextRuns,
  presetToCron,
  type RecurrenceFields,
  type RecurrencePreset,
} from "@/lib/routines/recurrence";

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

export function RecurrencePicker({ value, onChange, disabled = false }: RecurrencePickerProps) {
  const { t, i18n } = useAppI18n();
  const locale = i18n.language || "en-US";

  const cronExpression = useMemo(() => {
    if (value.recurrence.preset === "custom") {
      return value.customCron;
    }
    return presetToCron(value.recurrence);
  }, [value.recurrence, value.customCron]);

  const nextRuns = useMemo(() => {
    if (value.scheduleMode !== "recurring") return [];
    if (value.recurrence.preset === "custom") return [];
    return computeNextRuns(value.recurrence, 3);
  }, [value.scheduleMode, value.recurrence]);

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
      />

      {value.scheduleMode === "once" ? (
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,260px)]">
          <label className="flex flex-col gap-1.5">
            <span className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
              {t("routines.editor.dateTime")}
            </span>
            <Input
              type="datetime-local"
              value={value.oneShotAt}
              onChange={(event) => onChange(patch(value, { oneShotAt: event.target.value }))}
              disabled={disabled}
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
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
          />

          {value.recurrence.preset !== "hourly" && value.recurrence.preset !== "custom" ? (
            <div className="grid gap-3 md:grid-cols-2">
              <label className="flex flex-col gap-1.5">
                <span className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                  {t("routines.editor.timeOfDay")}
                </span>
                <Input
                  type="time"
                  value={value.recurrence.time}
                  onChange={(event) =>
                    onChange(
                      patch(value, {
                        recurrence: patch(value.recurrence, { time: event.target.value }),
                      }),
                    )
                  }
                  disabled={disabled}
                />
              </label>

              {value.recurrence.preset === "weekly" ? (
                <label className="flex flex-col gap-1.5">
                  <span className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
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
                  <span className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
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
            <label className="flex flex-col gap-1.5">
              <span className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                {t("routines.editor.customCron")}
              </span>
              <Input
                value={value.customCron}
                onChange={(event) => onChange(patch(value, { customCron: event.target.value }))}
                placeholder="0 9 * * 1"
                spellCheck={false}
                autoCorrect="off"
                autoCapitalize="off"
                className="font-mono"
                disabled={disabled}
              />
              <span className="text-[0.75rem] text-[var(--text-tertiary)]">
                {t("routines.editor.customCronHint")}
              </span>
            </label>
          ) : null}

          <label className="flex flex-col gap-1.5">
            <span className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
              {t("routines.editor.timezone")}
            </span>
            <TimezonePicker
              value={value.timezone}
              onValueChange={(tz) => onChange(patch(value, { timezone: tz }))}
              disabled={disabled}
            />
          </label>

          <div className="flex flex-col gap-2 rounded-[var(--radius-panel-sm)] border border-[var(--divider-hair)] bg-[var(--panel-soft)] px-3.5 py-3">
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                {t("routines.editor.cronExpression")}
              </span>
              {cronExpression ? (
                <span className="font-mono text-[0.75rem] text-[var(--text-secondary)]">
                  {cronExpression}
                </span>
              ) : null}
            </div>
            <div className="flex flex-col gap-1.5">
              <span className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                {t("routines.editor.nextRuns")}
              </span>
              {nextRuns.length > 0 ? (
                <ol className="m-0 flex flex-col gap-1 p-0">
                  {nextRuns.map((run, index) => (
                    <li
                      key={run.toISOString()}
                      className="flex items-baseline justify-between gap-3 text-[0.8125rem] text-[var(--text-secondary)]"
                    >
                      <span className="font-mono text-[var(--text-quaternary)]">#{index + 1}</span>
                      <span className="font-mono">{formatPreviewDate(run, value.timezone, locale)}</span>
                    </li>
                  ))}
                </ol>
              ) : (
                <span className="text-[0.8125rem] text-[var(--text-tertiary)]">
                  {t("routines.editor.nextRunsUnavailable")}
                </span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
