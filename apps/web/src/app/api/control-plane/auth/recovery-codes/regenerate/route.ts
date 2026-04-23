import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import { isTrustedDashboardRequest } from "@/lib/request-origin";
import { getWebOperatorTokenFromCookie } from "@/lib/web-operator-session";

const CONTROL_PLANE_BASE_URL = process.env.CONTROL_PLANE_BASE_URL || "http://127.0.0.1:8090";

const regenerateSchema = z
  .object({
    current_password: z.string().min(1, "Current password is required."),
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
      regenerateSchema,
      await request.json().catch(() => ({})),
      "Invalid regenerate payload.",
    );
    const upstream = await fetch(
      `${CONTROL_PLANE_BASE_URL.replace(/\/$/, "")}/api/control-plane/auth/recovery-codes/regenerate`,
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
        { error: String(data.error || "Unable to regenerate recovery codes.") },
        { status: upstream.status || 400, headers: { "Cache-Control": "no-store" } },
      );
    }
    return NextResponse.json(
      {
        ok: true,
        recovery_codes: Array.isArray(data.recovery_codes) ? data.recovery_codes : [],
        generated_at: typeof data.generated_at === "string" ? data.generated_at : null,
      },
      { status: 201, headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    return jsonErrorResponse(error, "Unable to regenerate recovery codes.");
  }
}
