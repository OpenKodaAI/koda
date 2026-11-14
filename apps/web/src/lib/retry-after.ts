/**
 * `Retry-After` on throttled responses (RFC 9110 §10.2.3).
 *
 * Both senders use delta-seconds. The control plane sends the whole seconds, rounded up,
 * until the bucket that refused the request takes the next one (`Retry-After: 360` after a
 * burst of recovery attempts). The dashboard proxy sends `Retry-After: 60`, the length of its
 * sliding window, after which its oldest counted request has expired. An HTTP-date in the
 * IMF-fixdate form every sender must generate is accepted too, so a reverse proxy in front of
 * the dashboard can use either.
 */

const DELTA_SECONDS = /^\d+$/;
const IMF_FIXDATE = /^[A-Z][a-z]{2}, \d{2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2} GMT$/;

/** Seconds the server asked the client to wait, or `null` when the value is absent or unusable. */
export function parseRetryAfterSeconds(
  value: string | null | undefined,
  now: number = Date.now(),
): number | null {
  const trimmed = value?.trim() ?? "";
  if (DELTA_SECONDS.test(trimmed)) {
    const seconds = Number(trimmed);
    return Number.isSafeInteger(seconds) ? seconds : null;
  }
  if (!IMF_FIXDATE.test(trimmed)) return null;
  const date = Date.parse(trimmed);
  if (Number.isNaN(date)) return null;
  // A date already past means the client may retry now.
  return Math.max(0, Math.ceil((date - now) / 1000));
}

/**
 * A wait as words in `language`: seconds under a minute, otherwise whole minutes rounded up,
 * so the wait shown is never shorter than the `seconds` the server asked for.
 */
export function formatRetryWait(seconds: number, language: string): string {
  const [value, unit] = seconds < 60 ? [seconds, "second"] : [Math.ceil(seconds / 60), "minute"];
  return new Intl.NumberFormat(language, { style: "unit", unit, unitDisplay: "long" }).format(value);
}
