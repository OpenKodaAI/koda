import { NextRequest, NextResponse } from "next/server";

import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import { z } from "zod";
import {
  clearWebOperatorSessionCookie,
  setWebOperatorSessionCookie,
} from "@/lib/web-operator-session";
import { isTrustedDashboardRequest } from "@/lib/request-origin";

const CONTROL_PLANE_BASE_URL =
  process.env.CONTROL_PLANE_BASE_URL || "http://127.0.0.1:8090";

const authPayloadSchema = z.object({
  token: z.string().trim().min(1, "Control plane token is required."),
});

async function exchangeLegacyToken(token: string): Promise<{ session_token?: string }> {
  const response = await fetch(
    `${CONTROL_PLANE_BASE_URL.replace(/\/$/, "")}/api/control-plane/auth/legacy/exchange`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ token }),
      cache: "no-store",
    },
  );
  if (!response.ok) {
    return {};
  }
  return (await response.json().catch(() => ({}))) as { session_token?: string };
}

export async function POST(request: NextRequest) {
  if (!isTrustedDashboardRequest(request)) {
    return NextResponse.json(
      { error: "Cross-site dashboard mutations are blocked." },
      { status: 403, headers: { "Cache-Control": "no-store" } },
    );
  }
  try {
    const payload = parseSchemaOrThrow(
      authPayloadSchema,
      await request.json().catch(() => ({})),
      "Invalid operator token payload.",
    );
    const token = payload.token.trim();
    const exchanged = await exchangeLegacyToken(token);
    if (!exchanged.session_token) {
      return NextResponse.json(
        { error: "Invalid control plane token." },
        { status: 401, headers: { "Cache-Control": "no-store" } },
      );
    }

    const response = NextResponse.json(
      { ok: true },
      { headers: { "Cache-Control": "no-store" } },
    );
    setWebOperatorSessionCookie(response, exchanged.session_token);
    return response;
  } catch (error) {
    return jsonErrorResponse(error, "Unable to establish operator session.");
  }
}

export async function DELETE(request: NextRequest) {
  if (!isTrustedDashboardRequest(request)) {
    return NextResponse.json(
      { error: "Cross-site dashboard mutations are blocked." },
      { status: 403, headers: { "Cache-Control": "no-store" } },
    );
  }
  const response = NextResponse.json(
    { ok: true },
    { headers: { "Cache-Control": "no-store" } },
  );
  clearWebOperatorSessionCookie(response);
  return response;
}
