import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import { isTrustedDashboardRequest } from "@/lib/request-origin";
import {
  setOwnerExistsHintCookie,
  setPendingRecoveryCookie,
  setWebOperatorSessionCookie,
} from "@/lib/web-operator-session";

const CONTROL_PLANE_BASE_URL = process.env.CONTROL_PLANE_BASE_URL || "http://127.0.0.1:8090";

// New (preferred) payload: email + password, bootstrap code or loopback-trusted request.
// Legacy `registration_token` still accepted for CLI-driven flows.
const registerSchema = z
  .object({
    email: z.string().trim().email("A valid email is required."),
    password: z.string().min(12, "Password must have at least 12 characters."),
    bootstrap_code: z.string().trim().optional().default(""),
    registration_token: z.string().trim().optional().default(""),
    username: z.string().trim().optional().default(""),
    display_name: z.string().trim().optional().default(""),
  })
  .strict();

export async function POST(request: NextRequest) {
  if (!isTrustedDashboardRequest(request)) {
    return NextResponse.json(
      { error: "Cross-site dashboard mutations are blocked." },
      { status: 403, headers: { "Cache-Control": "no-store" } },
    );
  }
  try {
    const payload = parseSchemaOrThrow(
      registerSchema,
      await request.json().catch(() => ({})),
      "Invalid registration payload.",
    );
    const upstream = await fetch(
      `${CONTROL_PLANE_BASE_URL.replace(/\/$/, "")}/api/control-plane/auth/register-owner`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        cache: "no-store",
      },
    );
    const data = (await upstream.json().catch(() => ({}))) as Record<string, unknown>;
    if (!upstream.ok || typeof data.session_token !== "string" || !data.session_token.trim()) {
      return NextResponse.json(
        { error: String(data.error || "Unable to create the owner account.") },
        { status: upstream.status || 400, headers: { "Cache-Control": "no-store" } },
      );
    }
    const response = NextResponse.json(
      {
        ok: true,
        auth: data.auth || null,
        operator: data.operator || null,
        recovery_codes: Array.isArray(data.recovery_codes) ? data.recovery_codes : [],
      },
      { status: 201, headers: { "Cache-Control": "no-store" } },
    );
    setWebOperatorSessionCookie(response, data.session_token);
    setOwnerExistsHintCookie(response, true);
    setPendingRecoveryCookie(response, true);
    return response;
  } catch (error) {
    return jsonErrorResponse(error, "Unable to create the owner account.");
  }
}
