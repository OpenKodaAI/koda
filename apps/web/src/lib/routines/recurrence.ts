import {
  addDays,
  addHours,
  addMonths,
  addWeeks,
  setDay,
  setDate,
  setHours,
  setMilliseconds,
  setMinutes,
  setSeconds,
  startOfHour,
} from "date-fns";

export type RecurrencePreset = "hourly" | "daily" | "weekly" | "monthly" | "custom";

export interface RecurrenceFields {
  preset: RecurrencePreset;
  time: string;
  weekday: number;
  day: number;
}

const TIME_PATTERN = /^(\d{1,2}):(\d{2})$/;

function parseTime(time: string): { hour: number; minute: number } {
  const match = TIME_PATTERN.exec(time);
  if (!match) return { hour: 9, minute: 0 };
  return {
    hour: Math.min(23, Math.max(0, Number(match[1]))),
    minute: Math.min(59, Math.max(0, Number(match[2]))),
  };
}

export function formatTime(hour: number, minute: number): string {
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

export function presetToCron(fields: RecurrenceFields): string {
  const { preset } = fields;
  if (preset === "hourly") {
    return "0 * * * *";
  }
  const { hour, minute } = parseTime(fields.time);
  if (preset === "daily") {
    return `${minute} ${hour} * * *`;
  }
  if (preset === "weekly") {
    const weekday = Math.min(6, Math.max(0, fields.weekday));
    return `${minute} ${hour} * * ${weekday}`;
  }
  if (preset === "monthly") {
    const day = Math.min(28, Math.max(1, fields.day));
    return `${minute} ${hour} ${day} * *`;
  }
  return "";
}

const PRESET_CRON_PATTERNS: Array<{
  preset: Exclude<RecurrencePreset, "custom">;
  match: RegExp;
}> = [
  { preset: "hourly", match: /^0 \* \* \* \*$/ },
  { preset: "daily", match: /^(\d+) (\d+) \* \* \*$/ },
  { preset: "weekly", match: /^(\d+) (\d+) \* \* (\d+)$/ },
  { preset: "monthly", match: /^(\d+) (\d+) (\d+) \* \*$/ },
];

export function cronToPreset(expr: string): RecurrenceFields | null {
  const trimmed = expr.trim();
  if (!trimmed) return null;

  for (const entry of PRESET_CRON_PATTERNS) {
    const match = entry.match.exec(trimmed);
    if (!match) continue;

    if (entry.preset === "hourly") {
      return { preset: "hourly", time: "00:00", weekday: 1, day: 1 };
    }

    const minute = Number(match[1]);
    const hour = Number(match[2]);
    const time = formatTime(hour, minute);

    if (entry.preset === "daily") {
      return { preset: "daily", time, weekday: 1, day: 1 };
    }
    if (entry.preset === "weekly") {
      return {
        preset: "weekly",
        time,
        weekday: Number(match[3]),
        day: 1,
      };
    }
    return {
      preset: "monthly",
      time,
      weekday: 1,
      day: Number(match[3]),
    };
  }
  return null;
}

function withTime(date: Date, hour: number, minute: number): Date {
  return setMilliseconds(setSeconds(setMinutes(setHours(date, hour), minute), 0), 0);
}

export function computeNextRuns(fields: RecurrenceFields, count = 3, now: Date = new Date()): Date[] {
  if (fields.preset === "custom") {
    return [];
  }

  if (fields.preset === "hourly") {
    const base = startOfHour(now);
    const first = base.getTime() <= now.getTime() ? addHours(base, 1) : base;
    return Array.from({ length: count }, (_, index) => addHours(first, index));
  }

  const { hour, minute } = parseTime(fields.time);

  if (fields.preset === "daily") {
    const candidate = withTime(now, hour, minute);
    const first = candidate.getTime() <= now.getTime() ? addDays(candidate, 1) : candidate;
    return Array.from({ length: count }, (_, index) => addDays(first, index));
  }

  if (fields.preset === "weekly") {
    const targetDay = Math.min(6, Math.max(0, fields.weekday));
    let candidate = setDay(withTime(now, hour, minute), targetDay, { weekStartsOn: 0 });
    if (candidate.getTime() <= now.getTime()) {
      candidate = addWeeks(candidate, 1);
    }
    return Array.from({ length: count }, (_, index) => addWeeks(candidate, index));
  }

  // monthly
  const targetDay = Math.min(28, Math.max(1, fields.day));
  let candidate = setDate(withTime(now, hour, minute), targetDay);
  if (candidate.getTime() <= now.getTime()) {
    candidate = addMonths(candidate, 1);
  }
  return Array.from({ length: count }, (_, index) => addMonths(candidate, index));
}

export function defaultRecurrenceFields(): RecurrenceFields {
  return {
    preset: "daily",
    time: "09:00",
    weekday: 1,
    day: 1,
  };
}

export type CronCellKey = "minute" | "hour" | "day" | "month" | "weekday";

export interface CronValidationError {
  cell: CronCellKey;
  code: "invalidChar" | "dayOutOfRange" | "monthOutOfRange" | "weekdayOutOfRange";
}

const CELL_ORDER: CronCellKey[] = ["minute", "hour", "day", "month", "weekday"];

export function validateCron(cron: string): CronValidationError | null {
  const segments = (cron ?? "").trim().split(/\s+/);
  for (let i = 0; i < CELL_ORDER.length; i += 1) {
    const cell = CELL_ORDER[i];
    const value = segments[i] ?? "*";
    if (value === "*") continue;
    if (!/^\d+$/.test(value)) {
      return { cell, code: "invalidChar" };
    }
    const n = Number(value);
    if (cell === "day" && n < 1) {
      return { cell, code: "dayOutOfRange" };
    }
    if (cell === "month" && n < 1) {
      return { cell, code: "monthOutOfRange" };
    }
    if (cell === "weekday" && n > 6) {
      return { cell, code: "weekdayOutOfRange" };
    }
  }
  return null;
}
