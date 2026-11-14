import { NextResponse } from "next/server";

import { parseRetryAfterSeconds } from "@/lib/retry-after";

/**
 * The dashboard's answer when the control plane throttled an auth call (ADR-038).
 *
 * The control plane answers `429` only from its per-client buckets, which count requests per
 * client address and behave the same whether or not the account exists. Passing the status
 * and `Retry-After` through lets the auth screens say how long to wait without telling the
 * caller anything about an account. The per-account lockout is not a `429`: it answers like
 * a wrong password, so it never reaches this helper and stays on the route's generic copy.
 *
 * Returns `null` for any other upstream response.
 */
export function rateLimitedAuthResponse(upstream: Response): NextResponse | null {
  if (upstream.status !== 429) return null;
  const retryAfterSeconds = parseRetryAfterSeconds(upstream.headers.get("Retry-After"));
  return NextResponse.json(
    { error: "Too many attempts. Try again later." },
    {
      status: 429,
      headers: {
        "Cache-Control": "no-store",
        ...(retryAfterSeconds === null ? {} : { "Retry-After": String(retryAfterSeconds) }),
      },
    },
  );
}
