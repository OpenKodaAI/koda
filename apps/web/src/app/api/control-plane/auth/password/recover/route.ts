import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
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
  try {
    const payload = parseSchemaOrThrow(
      recoverSchema,
      await request.json().catch(() => ({})),
      "Invalid recovery payload.",
    );
    const upstream = await fetch(
      `${CONTROL_PLANE_BASE_URL.replace(/\/$/, "")}/api/control-plane/auth/password/recover`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        cache: "no-store",
      },
    );
    const data = (await upstream.json().catch(() => ({}))) as Record<string, unknown>;
    if (!upstream.ok) {
      return NextResponse.json(
        { error: String(data.error || "Unable to reset password.") },
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
