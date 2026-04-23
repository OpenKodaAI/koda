import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import { isTrustedDashboardRequest } from "@/lib/request-origin";
import {
  setOwnerExistsHintCookie,
  setWebOperatorSessionCookie,
} from "@/lib/web-operator-session";

const CONTROL_PLANE_BASE_URL =
  process.env.CONTROL_PLANE_BASE_URL || "http://127.0.0.1:8090";

const loginSchema = z.object({
  identifier: z.string().trim().min(1, "Identifier is required."),
  password: z.string().min(1, "Password is required."),
});

export async function POST(request: NextRequest) {
  if (!isTrustedDashboardRequest(request)) {
    return NextResponse.json(
      { error: "Cross-site dashboard mutations are blocked." },
      { status: 403, headers: { "Cache-Control": "no-store" } },
    );
  }
  try {
    const payload = parseSchemaOrThrow(
      loginSchema,
      await request.json().catch(() => ({})),
      "Invalid login payload.",
    );
    const upstream = await fetch(
      `${CONTROL_PLANE_BASE_URL.replace(/\/$/, "")}/api/control-plane/auth/login`,
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
        { error: String(data.error || "Unable to sign in.") },
        { status: upstream.status || 400, headers: { "Cache-Control": "no-store" } },
      );
    }
    const response = NextResponse.json(
      { ok: true, auth: data.auth || null },
      { headers: { "Cache-Control": "no-store" } },
    );
    setWebOperatorSessionCookie(response, data.session_token);
    setOwnerExistsHintCookie(response, true);
    return response;
  } catch (error) {
    return jsonErrorResponse(error, "Unable to sign in.");
  }
}
