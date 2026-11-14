import { NextResponse } from "next/server";
import { INSECURE_TRANSPORT_ERROR_CODE } from "@/lib/web-operator-session-constants";

/**
 * Whether the operator cookies are marked `Secure`, and whether the browser
 * behind a request will keep them.
 *
 * A browser keeps a `Secure` cookie only on a secure context: an `https://`
 * page or a loopback host (`localhost`, `*.localhost`, `127.0.0.0/8`,
 * `[::1]`). Over plain HTTP from any other host it drops the cookie without an
 * error, so a sign-in the control plane accepted leaves no session and the
 * next page sends the operator back to `/setup` (D-085, J-14). The auth pages,
 * the routes that set the session cookie and the password-recover route ask
 * `insecureCookieTransport()` first and explain instead.
 */

type HeaderReader = { get(name: string): string | null | undefined };
type RequestUrl = { protocol: string; host: string } | string;

export type InsecureCookieTransport = {
  /** The plain-HTTP origin the browser used, e.g. `http://192.168.1.10:3000`. */
  origin: string;
};

function isTrue(value: string | undefined): boolean {
  return String(value).trim().toLowerCase() === "true";
}

/**
 * `Secure` on every operator cookie: always in production, where the
 * development-only `ALLOW_INSECURE_COOKIES` has no effect, and in development
 * only with `SECURE_COOKIES=true`.
 */
export function secureCookiesEnabled(): boolean {
  if (process.env.NODE_ENV === "production") return true;
  return isTrue(process.env.SECURE_COOKIES) && !isTrue(process.env.ALLOW_INSECURE_COOKIES);
}

/** Hosts a browser treats as a secure context even over plain HTTP. */
export function isLoopbackHostname(hostname: string): boolean {
  const host = hostname.trim().toLowerCase().replace(/\.$/, "");
  if (host === "localhost" || host.endsWith(".localhost")) return true;
  if (host === "[::1]" || host === "::1") return true;
  return /^127\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(host);
}

function parseWebOrigin(value: string): URL | null {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}

function firstHop(value: string | null | undefined): string {
  return String(value ?? "").split(",")[0].trim();
}

/** The origin in the browser's address bar, or null when it is secure or unknown. */
function plainHttpOrigin(headers: HeaderReader, requestUrl?: RequestUrl): URL | null {
  // A browser names its own origin on every POST and cross-origin request.
  const origin = headers.get("origin")?.trim();
  if (origin && origin !== "null") return parseWebOrigin(origin);

  // Fetch Metadata headers are sent only to a potentially trustworthy URL, so
  // the page that sent them keeps Secure cookies, even behind a TLS proxy that
  // sends no X-Forwarded-Proto.
  if (headers.get("sec-fetch-site") || headers.get("sec-fetch-mode")) return null;

  // Otherwise the scheme and host the request arrived with. Next.js fills in
  // X-Forwarded-Proto and X-Forwarded-Host from the socket and the Host header
  // when no proxy set them.
  const url = typeof requestUrl === "string" ? parseWebOrigin(requestUrl) : requestUrl;
  const proto =
    firstHop(headers.get("x-forwarded-proto")).toLowerCase() ||
    (url?.protocol ?? "").replace(/:$/, "");
  const host = firstHop(headers.get("x-forwarded-host")) || headers.get("host")?.trim() || url?.host || "";
  if (!proto || !host) return null;
  return parseWebOrigin(`${proto}://${host}`);
}

/**
 * The `[cookie-transport]` logging window. It opens with the first warning
 * after the last one closed; within it each origin is named at most once.
 */
export const INSECURE_TRANSPORT_LOG_INTERVAL_MS = 60 * 60 * 1000;
/**
 * Most origins named per window, so made-up `Origin` and `Host` headers cannot
 * flood the log. Requests from later origins are counted instead.
 */
export const INSECURE_TRANSPORT_LOG_MAX_ORIGINS = 32;

type LogWindow = {
  /** When the window opened, in epoch milliseconds. */
  start: number;
  /** The origins named in this window; never more than the cap. */
  named: Set<string>;
  /** Requests refused in this window from origins past the cap, which go unnamed. */
  unnamed: number;
};

// Next.js bundles this module separately for the proxy, the pages and each
// route, so the window lives on globalThis, one per process.
const LOG_STATE_KEY = Symbol.for("koda.web.insecure-cookie-transport-log-window");
type LogStateHost = typeof globalThis & { [LOG_STATE_KEY]?: LogWindow };

function windowEnd(logWindow: LogWindow): string {
  return new Date(logWindow.start + INSECURE_TRANSPORT_LOG_INTERVAL_MS).toISOString();
}

function unnamedCountLine(logWindow: LogWindow): string {
  const requests =
    logWindow.unnamed === 1
      ? "1 plain-HTTP request from an address that was not named was"
      : `${logWindow.unnamed} plain-HTTP requests from addresses that were not named were`;
  return `[cookie-transport] ${requests} refused between ${new Date(logWindow.start).toISOString()} and ${windowEnd(logWindow)}.`;
}

/**
 * Warn once per origin per window. The origin comes from the request's headers,
 * which any client can set, so one line per origin keeps a scanner's made-up
 * address from standing in for the operator's own, and the cap bounds what a
 * stream of made-up hosts can write. Past the cap one line says that addresses
 * are no longer named, and the first warning after the window gives the count,
 * so a scanner can push the operator's address out of the log but not hide that
 * it did.
 */
function logInsecureTransport(origin: string): void {
  const host = globalThis as LogStateHost;
  const now = Date.now();
  let current = host[LOG_STATE_KEY];
  if (current && now - current.start >= INSECURE_TRANSPORT_LOG_INTERVAL_MS) {
    if (current.unnamed > 0) console.warn(unnamedCountLine(current));
    current = undefined;
  }
  if (!current) {
    current = { start: now, named: new Set(), unnamed: 0 };
    host[LOG_STATE_KEY] = current;
  }
  if (current.named.has(origin)) return;
  if (current.named.size < INSECURE_TRANSPORT_LOG_MAX_ORIGINS) {
    current.named.add(origin);
    console.warn(
      `[cookie-transport] A browser opened the dashboard over plain HTTP at ${origin}. Session cookies are Secure, so sign-in is refused there; serve the dashboard over HTTPS through a reverse proxy, or open it at a localhost address.`,
    );
    return;
  }
  if (current.unnamed === 0) {
    console.warn(
      `[cookie-transport] More than ${INSECURE_TRANSPORT_LOG_MAX_ORIGINS} addresses opened the dashboard over plain HTTP since ${new Date(current.start).toISOString()}. Further addresses are still refused, but not named before ${windowEnd(current)}; the first plain-HTTP request after that logs how many requests went unnamed.`,
    );
  }
  current.unnamed += 1;
}

/**
 * The plain-HTTP origin of a request whose browser will drop the operator
 * cookies, or null when they will be kept or the transport cannot be told.
 * What the browser says (Origin, Fetch Metadata) outranks the forwarded
 * headers, so a current browser behind a TLS proxy is not refused even when
 * the proxy sends no X-Forwarded-Proto.
 */
export function insecureCookieTransport(
  headers: HeaderReader,
  requestUrl?: RequestUrl,
): InsecureCookieTransport | null {
  if (!secureCookiesEnabled()) return null;
  const url = plainHttpOrigin(headers, requestUrl);
  if (!url || url.protocol !== "http:" || isLoopbackHostname(url.hostname)) return null;
  logInsecureTransport(url.origin);
  return { origin: url.origin };
}

/**
 * The refusal an auth route returns over plain HTTP, before it contacts the
 * control plane: signing in or registering the owner there would start a
 * session the browser throws away, registration would spend the one-time setup
 * code, and recovery would send the recovery code and the new password in clear
 * text only to end on a sign-in that cannot last. `code` lets the screens show
 * their own copy.
 */
export function insecureCookieTransportResponse(transport: InsecureCookieTransport): NextResponse {
  return NextResponse.json(
    {
      error: {
        code: INSECURE_TRANSPORT_ERROR_CODE,
        message: `This dashboard was opened over plain HTTP at ${transport.origin}. Its session cookies are Secure, so the browser would drop them.`,
        user_action: "Serve it over HTTPS through a reverse proxy, or open it at a localhost address.",
      },
    },
    { status: 403, headers: { "Cache-Control": "no-store" } },
  );
}
