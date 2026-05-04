/**
 * Whitelist for the `?next=` parameter used by the auth flow to round-trip the
 * pre-login URL. Rejecting unsafe targets here prevents open-redirect abuse
 * (e.g. `?next=//attacker.com` or `?next=javascript:...`) and keeps the
 * post-login navigation strictly inside this app.
 */
const SAFE_REDIRECT_PATTERN = /^\/(?!\/)[^?#]*(?:\?[^#]*)?$/;
const FORBIDDEN_PREFIXES: ReadonlyArray<string> = ["/api/", "/oauth/", "/_next/"];

export function isSafeRedirectTarget(value: string | null | undefined): value is string {
  if (!value || typeof value !== "string") return false;
  if (!SAFE_REDIRECT_PATTERN.test(value)) return false;
  if (FORBIDDEN_PREFIXES.some((prefix) => value.startsWith(prefix))) return false;
  return true;
}

export function safeRedirectTarget(
  value: string | null | undefined,
  fallback = "/",
): string {
  return isSafeRedirectTarget(value) ? value : fallback;
}
