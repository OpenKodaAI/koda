/**
 * Client address for per-client rate limiting, in the dashboard and in the
 * control plane behind it.
 *
 * Next.js sets `x-forwarded-for` to the TCP peer address when a request
 * arrives without one, and a reverse proxy in front of the dashboard appends
 * the address it accepted the connection from. Either way the rightmost entry
 * was written by infrastructure, not by the browser; anything to its left is
 * client-supplied and ignored.
 *
 * The control plane believes the forwarded value only from trusted proxies
 * (`CONTROL_PLANE_TRUSTED_PROXIES`, which covers the dashboard by default).
 */

type HeaderSource =
  | { get(name: string): string | null | undefined }
  | null
  | undefined;

const IPV4 = /^\d{1,3}(?:\.\d{1,3}){3}$/;
const IPV6 = /^[0-9a-f]*:[0-9a-f:.]*$/i;

export function clientIpFromHeaders(headers: HeaderSource): string | null {
  const raw = typeof headers?.get === "function" ? headers.get("x-forwarded-for") : null;
  if (!raw) return null;
  const hops = raw.split(",");
  const last = hops[hops.length - 1]?.trim() ?? "";
  if (last.length > 45 || !(IPV4.test(last) || IPV6.test(last))) return null;
  return last.toLowerCase();
}

/** Header to send upstream so the control plane buckets the request by its client. */
export function forwardedClientIpHeaders(headers: HeaderSource): Record<string, string> {
  const ip = clientIpFromHeaders(headers);
  return ip ? { "X-Forwarded-For": ip } : {};
}
