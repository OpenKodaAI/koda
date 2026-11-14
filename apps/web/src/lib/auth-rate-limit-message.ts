import { ApiError } from "@/lib/errors";
import type { AppTranslator } from "@/lib/i18n";
import { formatRetryWait } from "@/lib/retry-after";

/**
 * The auth screens' message for a throttled attempt, or `null` when `error` is not one.
 *
 * Only a `429` qualifies: the per-client rate limit, which reveals nothing about an account
 * (ADR-038). Every identity failure (wrong password, unknown user, locked account, invalid
 * code) arrives with another status and keeps the screen's single generic message.
 */
export function rateLimitedAuthMessage(
  error: unknown,
  t: AppTranslator,
  language: string,
): string | null {
  if (!(error instanceof ApiError) || error.status !== 429) return null;
  const seconds = error.retryAfterSeconds;
  if (seconds === null || seconds <= 0) {
    return t("auth.rate_limited.no_wait");
  }
  return t("auth.rate_limited.with_wait", { duration: formatRetryWait(seconds, language) });
}
