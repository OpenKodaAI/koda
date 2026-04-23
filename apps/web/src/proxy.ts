import { NextRequest, NextResponse } from "next/server";
import { isMutationMethod, isTrustedDashboardRequest } from "@/lib/request-origin";
import { WEB_OPERATOR_SESSION_COOKIE } from "@/lib/web-operator-session-constants";

/* ---------- sliding-window rate limiter ---------- */

const RATE_LIMIT_WINDOW_MS = 60_000;
const RATE_LIMIT_MAX_REQUESTS = 120;
const PUBLIC_CONTROL_PLANE_PATHS = new Set([
  "/api/control-plane/onboarding/status",
  "/api/control-plane/auth/status",
  "/api/control-plane/auth/bootstrap/exchange",
  "/api/control-plane/auth/login",
  "/api/control-plane/auth/register-owner",
]);

interface SlidingWindow {
  timestamps: number[];
  updatedAt: number;
}

const ipWindows = new Map<string, SlidingWindow>();

/** Evict stale entries every 5 minutes to prevent unbounded growth. */
const EVICTION_INTERVAL_MS = 5 * 60_000;
let lastEviction = Date.now();

function evictStaleEntries(now: number) {
  if (now - lastEviction < EVICTION_INTERVAL_MS) return;
  lastEviction = now;
  for (const [ip, window] of ipWindows) {
    if (now - window.updatedAt > RATE_LIMIT_WINDOW_MS * 2) {
      ipWindows.delete(ip);
    }
  }
}

function isRateLimited(ip: string): boolean {
  const now = Date.now();
  evictStaleEntries(now);

  let window = ipWindows.get(ip);
  if (!window) {
    window = { timestamps: [], updatedAt: now };
    ipWindows.set(ip, window);
  }

  // Remove timestamps outside the sliding window.
  const cutoff = now - RATE_LIMIT_WINDOW_MS;
  window.timestamps = window.timestamps.filter((t) => t > cutoff);
  window.updatedAt = now;

  if (window.timestamps.length >= RATE_LIMIT_MAX_REQUESTS) {
    return true;
  }

  window.timestamps.push(now);
  return false;
}

const TRUSTED_PROXY_IPS = new Set(
  (process.env.TRUSTED_PROXY_IPS || "127.0.0.1,::1,::ffff:127.0.0.1").split(",").map((s) => s.trim()),
);

function clientIp(request: NextRequest): string {
  const directIp = (request as NextRequest & { ip?: string }).ip || "unknown";
  const forwardedFor = request.headers?.get?.("x-forwarded-for");
  // Only trust x-forwarded-for when request arrives through a known proxy
  if (forwardedFor && TRUSTED_PROXY_IPS.has(directIp)) {
    return forwardedFor.split(",")[0]?.trim() || directIp;
  }
  return directIp;
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

const LOGIN_RATE_LIMIT_MAX = 20;
const loginIpWindows = new Map<string, SlidingWindow>();

function evictStaleLoginEntries(now: number) {
  if (now - lastEviction < EVICTION_INTERVAL_MS) return;
  for (const [ip, window] of loginIpWindows) {
    if (now - window.updatedAt > RATE_LIMIT_WINDOW_MS * 2) {
      loginIpWindows.delete(ip);
    }
  }
}

function isLoginRateLimited(ip: string): boolean {
  const now = Date.now();
  evictStaleLoginEntries(now);
  let window = loginIpWindows.get(ip);
  if (!window) {
    window = { timestamps: [], updatedAt: now };
    loginIpWindows.set(ip, window);
  }
  const cutoff = now - RATE_LIMIT_WINDOW_MS;
  window.timestamps = window.timestamps.filter((t) => t > cutoff);
  window.updatedAt = now;
  if (window.timestamps.length >= LOGIN_RATE_LIMIT_MAX) {
    return true;
  }
  window.timestamps.push(now);
  return false;
}

function isLoginSessionPath(pathname: string): boolean {
  return /\/api\/control-plane\/providers\/[^/]+\/connection\/login\//.test(pathname);
}

function isPublicControlPlanePath(pathname: string): boolean {
  return PUBLIC_CONTROL_PLANE_PATHS.has(pathname);
}

function developmentAuthBypassEnabled(): boolean {
  return (
    process.env.NODE_ENV !== "production" &&
    String(process.env.CONTROL_PLANE_AUTH_MODE).trim().toLowerCase() === "development"
  );
}

export function proxy(request: NextRequest) {
  // Rate limit all matched API routes.
  // Login session paths get a more permissive limit instead of full exemption.
  const ip = clientIp(request);
  if (isLoginSessionPath(request.nextUrl.pathname)) {
    // Separate, more permissive rate limit for login session polling (20 req/min)
    if (isLoginRateLimited(ip)) {
      return rateLimitedResponse();
    }
  } else if (isRateLimited(ip)) {
    return rateLimitedResponse();
  }

  if (isMutationMethod(request.method) && !isTrustedDashboardRequest(request)) {
    return forbiddenMutationResponse();
  }

  if (isPublicControlPlanePath(request.nextUrl.pathname)) {
    return NextResponse.next();
  }
  if (developmentAuthBypassEnabled()) {
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

export const config = {
  matcher: ["/api/control-plane/:path*", "/api/runtime/:path*", "/api/channels/:path*"],
};
