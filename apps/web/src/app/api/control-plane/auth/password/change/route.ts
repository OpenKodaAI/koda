import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import { isTrustedDashboardRequest } from "@/lib/request-origin";
import { getWebOperatorTokenFromCookie } from "@/lib/web-operator-session";

const CONTROL_PLANE_BASE_URL = process.env.CONTROL_PLANE_BASE_URL || "http://127.0.0.1:8090";

const changeSchema = z
  .object({
    current_password: z.string().min(1, "Current password is required."),
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
  const token = await getWebOperatorTokenFromCookie();
  if (!token) {
    return NextResponse.json(
      { error: "Operator session is required." },
      { status: 401, headers: { "Cache-Control": "no-store" } },
    );
  }
  try {
    const payload = parseSchemaOrThrow(
      changeSchema,
      await request.json().catch(() => ({})),
      "Invalid password-change payload.",
    );
    const upstream = await fetch(
      `${CONTROL_PLANE_BASE_URL.replace(/\/$/, "")}/api/control-plane/auth/password/change`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
        cache: "no-store",
      },
    );
    const data = (await upstream.json().catch(() => ({}))) as Record<string, unknown>;
    if (!upstream.ok) {
      return NextResponse.json(
        { error: String(data.error || "Unable to change password.") },
        { status: upstream.status || 400, headers: { "Cache-Control": "no-store" } },
      );
    }
    return NextResponse.json(
      { ok: true },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    return jsonErrorResponse(error, "Unable to change password.");
  }
}
