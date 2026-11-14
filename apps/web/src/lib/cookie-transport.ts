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
 * next page sends the operator back to `/setup` (D-085, J-14). The auth pages
 * and the routes that set the session cookie ask `insecureCookieTransport()`
 * first and explain instead.
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

// Next.js bundles this module separately for the proxy, the pages and each
// route, so the "logged once" flag lives on globalThis to hold per process.
const LOGGED_KEY = Symbol.for("koda.web.insecure-cookie-transport-logged");
type LoggedFlagHost = typeof globalThis & { [LOGGED_KEY]?: boolean };

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
  const flagHost = globalThis as LoggedFlagHost;
  if (!flagHost[LOGGED_KEY]) {
    flagHost[LOGGED_KEY] = true;
    console.warn(
      `[cookie-transport] A browser opened the dashboard over plain HTTP at ${url.origin}. Session cookies are Secure, so sign-in is refused there; serve the dashboard over HTTPS through a reverse proxy, or open it at a localhost address.`,
    );
  }
  return { origin: url.origin };
}

/**
 * The refusal a route that sets the session cookie returns over plain HTTP,
 * before it contacts the control plane: signing in or registering the owner
 * there would start a session the browser throws away, and registration would
 * spend the one-time setup code. `code` lets the screens show their own copy.
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
