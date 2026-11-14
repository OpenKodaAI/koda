import { NextRequest, NextResponse } from "next/server";
import { clientIpFromHeaders, rateLimitKey } from "@/lib/client-ip";
import { isPublicControlPlaneApiPath } from "@/lib/public-control-plane-paths";
import { isMutationMethod, isTrustedDashboardRequest } from "@/lib/request-origin";
import { unsealWebOperatorToken } from "@/lib/web-operator-session";
import {
  OWNER_EXISTS_HINT_COOKIE,
  PENDING_RECOVERY_COOKIE,
  WEB_OPERATOR_SESSION_COOKIE,
} from "@/lib/web-operator-session-constants";
import { isSafeRedirectTarget } from "@/lib/safe-redirect";
import { createSlidingWindowLimiter } from "@/lib/sliding-window-limiter";

/* ---------- page-level auth gate ---------- */

const SETUP_PATH = "/setup";
const LOGIN_PATH = "/login";
const FORGOT_PATH = "/forgot-password";
const AUTH_PATHS: ReadonlyArray<string> = [LOGIN_PATH, FORGOT_PATH, SETUP_PATH];

const ALLOW_INSECURE_COOKIES =
  process.env.NODE_ENV !== "production" &&
  String(process.env.ALLOW_INSECURE_COOKIES).trim().toLowerCase() === "true";
const SECURE_COOKIES =
  !ALLOW_INSECURE_COOKIES &&
  (process.env.NODE_ENV === "production" ||
    String(process.env.SECURE_COOKIES).trim().toLowerCase() === "true");

function isPublicAssetPath(pathname: string): boolean {
  return (
    pathname.startsWith("/_next/") ||
    pathname.startsWith("/oauth/") ||
    pathname === "/favicon.ico" ||
    pathname === "/robots.txt" ||
    pathname === "/sitemap.xml" ||
    pathname.startsWith("/apple-icon") ||
    pathname.startsWith("/icon") ||
    pathname.endsWith(".svg") ||
    pathname.endsWith(".png") ||
    pathname.endsWith(".webp") ||
    pathname.endsWith(".ico")
  );
}

function isAuthPath(pathname: string): boolean {
  return AUTH_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

function clearSessionCookie(response: NextResponse): void {
  response.cookies.set({
    name: WEB_OPERATOR_SESSION_COOKIE,
    value: "",
    httpOnly: true,
    sameSite: "strict",
    path: "/",
    maxAge: 0,
    secure: SECURE_COOKIES,
  });
}

function buildSafeNext(pathname: string, search: string): string | null {
  const target = `${pathname}${search ?? ""}`;
  return isSafeRedirectTarget(target) ? target : null;
}

function pageAuthGate(request: NextRequest): NextResponse {
  const { pathname, search } = request.nextUrl;

  const forwardedHeaders = new Headers(request.headers);
  for (const key of Array.from(forwardedHeaders.keys())) {
    if (key.toLowerCase().startsWith("x-koda-")) {
      forwardedHeaders.delete(key);
    }
  }
  forwardedHeaders.set("x-koda-pathname", pathname);

  const passThrough = () =>
    NextResponse.next({ request: { headers: forwardedHeaders } });

  const sealed = request.cookies.get(WEB_OPERATOR_SESSION_COOKIE)?.value ?? "";
  const sessionToken = sealed ? unsealWebOperatorToken(sealed) : null;
  const sessionMalformed = Boolean(sealed) && !sessionToken;
  const isAuthenticated = Boolean(sessionToken);

  const hasOwnerHint = request.cookies.get(OWNER_EXISTS_HINT_COOKIE)?.value === "1";
  const hasPendingRecovery =
    request.cookies.get(PENDING_RECOVERY_COOKIE)?.value === "1";
  const inAuthRoute = isAuthPath(pathname);

  if (isAuthenticated) {
    if (pathname === SETUP_PATH && hasPendingRecovery) {
      return passThrough();
    }
    // Auth routes pass through so the page itself can validate the sealed
    // token against the control plane and decide. Redirecting blindly here
    // creates a loop with the layout when the backend has revoked the token
    // but the local seal still decrypts.
    return passThrough();
  }

  if (inAuthRoute) {
    if (pathname === SETUP_PATH && hasOwnerHint && !hasPendingRecovery) {
      const target = request.nextUrl.clone();
      target.pathname = LOGIN_PATH;
      target.search = "";
      const setupNext = request.nextUrl.searchParams.get("next");
      if (isSafeRedirectTarget(setupNext)) {
        target.searchParams.set("next", setupNext);
      }
      const response = NextResponse.redirect(target);
      if (sessionMalformed) clearSessionCookie(response);
      return response;
    }
    const response = passThrough();
    if (sessionMalformed) clearSessionCookie(response);
    return response;
  }

  const target = request.nextUrl.clone();
  target.pathname = hasOwnerHint ? LOGIN_PATH : SETUP_PATH;
  target.search = "";

  const safeNext = buildSafeNext(pathname, search);
  if (safeNext) {
    target.searchParams.set("next", safeNext);
  }

  const response = NextResponse.redirect(target);
  if (sessionMalformed) clearSessionCookie(response);
  return response;
}

/* ---------- sliding-window rate limiter ---------- */

const RATE_LIMIT_MAX_REQUESTS = 120;
const LOGIN_RATE_LIMIT_MAX = 20;

// Separate per-client windows, each with its own eviction schedule and size cap.
const apiWindow = createSlidingWindowLimiter({ maxRequests: RATE_LIMIT_MAX_REQUESTS });
const loginSessionWindow = createSlidingWindowLimiter({ maxRequests: LOGIN_RATE_LIMIT_MAX });

/** Rate-limit key of the client behind the request (an IPv6 client's /64). */
function clientKey(request: NextRequest): string {
  const ip = clientIpFromHeaders(request.headers);
  return ip ? rateLimitKey(ip) : "unknown";
}

/* ---------- responses ---------- */

function rateLimitedResponse() {
  return NextResponse.json(
    { error: "rate limit exceeded" },
    {
      status: 429,
      headers: {
        "Retry-After": "60",
        "Cache-Control": "no-store",
      },
    },
  );
}

function unauthorizedResponse() {
  return NextResponse.json(
    { error: "Operator session is required." },
    {
      status: 401,
      headers: {
        "Cache-Control": "no-store",
      },
    },
  );
}

function forbiddenMutationResponse() {
  return NextResponse.json(
    { error: "Cross-site dashboard mutations are blocked." },
    {
      status: 403,
      headers: {
        "Cache-Control": "no-store",
      },
    },
  );
}

/* ---------- proxy ---------- */

function isLoginSessionPath(pathname: string): boolean {
  return /\/api\/control-plane\/providers\/[^/]+\/connection\/login\//.test(pathname);
}

function apiProxyGate(request: NextRequest): NextResponse {
  const limiter = isLoginSessionPath(request.nextUrl.pathname) ? loginSessionWindow : apiWindow;
  if (limiter.isLimited(clientKey(request))) {
    return rateLimitedResponse();
  }

  if (isMutationMethod(request.method) && !isTrustedDashboardRequest(request)) {
    return forbiddenMutationResponse();
  }

  if (isPublicControlPlaneApiPath(request.nextUrl.pathname)) {
    return NextResponse.next();
  }

  const hasOperatorSession = Boolean(
    request.cookies.get(WEB_OPERATOR_SESSION_COOKIE)?.value?.trim(),
  );
  if (!hasOperatorSession) {
    return unauthorizedResponse();
  }

  return NextResponse.next();
}

const API_GATED_PREFIXES: ReadonlyArray<string> = [
  "/api/control-plane/",
  "/api/runtime/",
  "/api/channels/",
];

function isApiGatedPath(pathname: string): boolean {
  return API_GATED_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // API surfaces handled by the dedicated rate-limited + auth gate.
  if (isApiGatedPath(pathname)) {
    return apiProxyGate(request);
  }

  // Static + framework + OAuth callbacks pass straight through.
  if (isPublicAssetPath(pathname) || pathname.startsWith("/api/")) {
    return NextResponse.next();
  }

  // Page routes: cookie-format auth gate that redirects unauthenticated
  // traffic to /login (or /setup if no owner is registered yet).
  return pageAuthGate(request);
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|_next/webpack-hmr|favicon.ico|apple-icon.png|robots.txt|sitemap.xml).*)",
  ],
};
