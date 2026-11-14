import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import {
  jsonErrorResponse,
  parseSchemaOrThrow,
  upstreamFetch,
} from "@/lib/api-utils";
import { rateLimitedAuthResponse } from "@/lib/auth-rate-limited-response";
import { forwardedClientIpHeaders } from "@/lib/client-ip";
import { insecureCookieTransport, insecureCookieTransportResponse } from "@/lib/cookie-transport";
import { isTrustedDashboardRequest } from "@/lib/request-origin";

const CONTROL_PLANE_BASE_URL = process.env.CONTROL_PLANE_BASE_URL || "http://127.0.0.1:8090";

const recoverSchema = z
  .object({
    identifier: z.string().trim().min(1, "Identifier is required."),
    recovery_code: z.string().trim().min(1, "Recovery code is required."),
    new_password: z.string().min(12, "Password must have at least 12 characters."),
  })
  .strict();

export async function POST(request: NextRequest) {
  if (!isTrustedDashboardRequest(request)) {
    return NextResponse.json(
      { error: "Cross-site dashboard mutations are blocked." },
      { status: 403, headers: { "Cache-Control": "no-store" } },
    );
  }
  // Over plain HTTP from a non-loopback host the recovery code and the new
  // password would cross the network in clear text, and the reset would end on
  // a /login that cannot sign in from this browser. Refuse before the control
  // plane consumes the code and revokes every session (J-14).
  const insecureTransport = insecureCookieTransport(request.headers, request.nextUrl);
  if (insecureTransport) {
    return insecureCookieTransportResponse(insecureTransport);
  }
  try {
    const payload = parseSchemaOrThrow(
      recoverSchema,
      await request.json().catch(() => ({})),
      "Invalid recovery payload.",
    );
    const upstream = await upstreamFetch(
      `${CONTROL_PLANE_BASE_URL.replace(/\/$/, "")}/api/control-plane/auth/password/recover`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...forwardedClientIpHeaders(request.headers),
        },
        body: JSON.stringify(payload),
        cache: "no-store",
      },
      { label: "Recovery service" },
    );
    // The per-client rate limit keeps its 429 and wait: it is the same for every
    // identifier, so it reveals nothing about an account (ADR-038).
    const rateLimited = rateLimitedAuthResponse(upstream);
    if (rateLimited) return rateLimited;
    if (!upstream.ok) {
      // Generic message — recovery flow is also identifier-bearing and must
      // stay indistinguishable across "unknown user" / "wrong code" / "locked
      // account" (CLAUDE.md auth contract).
      return NextResponse.json(
        { error: "Invalid recovery details." },
        { status: upstream.status || 400, headers: { "Cache-Control": "no-store" } },
      );
    }
    return NextResponse.json(
      { ok: true },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    return jsonErrorResponse(error, "Unable to reset password.");
  }
}
