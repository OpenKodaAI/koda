/**
 * Client address for per-client rate limiting, in the dashboard and in the
 * control plane behind it.
 *
 * server.mjs rewrites `x-forwarded-for` on every request before Next.js sees
 * it (`forwarded-for.mjs`). The new value is a single address resolved from
 * the TCP socket: the peer itself, or, when the peer is a trusted proxy
 * (loopback or `WEB_TRUSTED_PROXIES`), the client that proxy reported. A
 * client that reaches the dashboard directly cannot choose it by sending its
 * own header. Only the rightmost entry is read, so a header with several
 * entries (server.mjs never sends one) resolves to the last hop rather than a
 * client-supplied one.
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
const IPV4_MAPPED = /^::ffff:(\d{1,3}(?:\.\d{1,3}){3})$/;
const HEXTET = /^[0-9a-f]{1,4}$/;

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

/** Loopback addresses, which the control plane's dev-only bootstrap trust accepts. */
export function isLoopbackAddress(ip: string | null): boolean {
  return ip === "127.0.0.1" || ip === "::1" || ip === "::ffff:127.0.0.1";
}

/** First 64 bits of an IPv6 address as `a:b:c:d::/64`, or null if it does not parse. */
function ipv6Prefix64(ip: string): string | null {
  const halves = ip.split("::");
  if (halves.length > 2) return null;
  const head = halves[0] ? halves[0].split(":") : [];
  const tail = halves.length === 2 && halves[1] ? halves[1].split(":") : [];
  // An embedded IPv4 tail (64:ff9b::192.0.2.1) fills two hextets.
  const width = (groups: string[]) => groups.reduce((total, group) => total + (group.includes(".") ? 2 : 1), 0);
  const missing = 8 - width(head) - width(tail);
  if (halves.length === 2 ? missing < 1 : missing !== 0) return null;
  const groups = [...head, ...Array<string>(halves.length === 2 ? missing : 0).fill("0"), ...tail];
  const prefix = groups.slice(0, 4);
  if (!prefix.every((group) => HEXTET.test(group))) return null;
  return `${prefix.map((group) => Number.parseInt(group, 16).toString(16)).join(":")}::/64`;
}

/**
 * Rate-limit key for a client address. IPv6 clients are grouped by their /64,
 * the block a single subscriber normally gets, so rotating source addresses
 * inside it does not buy a fresh window.
 */
export function rateLimitKey(ip: string): string {
  const normalized = ip.toLowerCase();
  const mapped = IPV4_MAPPED.exec(normalized);
  if (mapped) return mapped[1];
  if (!normalized.includes(":")) return normalized;
  return ipv6Prefix64(normalized) ?? normalized;
}
