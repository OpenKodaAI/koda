export type RecurrencePreset = "hourly" | "daily" | "weekly" | "monthly" | "interval" | "custom";

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

export function defaultRecurrenceFields(): RecurrenceFields {
  return {
    preset: "daily",
    time: "09:00",
    weekday: 1,
    day: 1,
  };
}

// One-shot times are wall-clock "YYYY-MM-DDTHH:mm" values in the routine's timezone, which can
// differ from the browser's (D-081). Cron and interval previews come from the scheduler itself.

function zonedParts(date: Date, timeZone: string) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((entry) => entry.type === type)?.value ?? 0);
  return {
    year: part("year"),
    month: part("month"),
    day: part("day"),
    hour: part("hour"),
    minute: part("minute"),
    second: part("second"),
  };
}

function zoneOffsetMs(date: Date, timeZone: string): number {
  const p = zonedParts(date, timeZone);
  const wallAsUtc = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
  return wallAsUtc - (date.getTime() - date.getMilliseconds());
}

/** The wall-clock time of `date` in `timeZone`, as "YYYY-MM-DDTHH:mm". */
export function utcToZonedWallTime(date: Date, timeZone: string): string {
  const p = zonedParts(date, timeZone);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${p.year}-${pad(p.month)}-${pad(p.day)}T${pad(p.hour)}:${pad(p.minute)}`;
}

/** The instant at which the wall clock in `timeZone` reads `wall` ("YYYY-MM-DDTHH:mm"). */
export function zonedWallTimeToUtc(wall: string, timeZone: string): Date {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(wall.trim());
  if (!match) return new Date(Number.NaN);
  const [, year, month, day, hour, minute] = match.map(Number);
  const wallAsUtc = Date.UTC(year, month - 1, day, hour, minute);
  // Two passes settle the offset when the first guess lands across a DST change.
  let instant = wallAsUtc - zoneOffsetMs(new Date(wallAsUtc), timeZone);
  instant = wallAsUtc - zoneOffsetMs(new Date(instant), timeZone);
  return new Date(instant);
}
