import { NextRequest, NextResponse } from "next/server";

import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import { z } from "zod";
import {
  clearWebOperatorSessionCookie,
  setWebOperatorSessionCookie,
} from "@/lib/web-operator-session";

const CONTROL_PLANE_BASE_URL =
  process.env.CONTROL_PLANE_BASE_URL || "http://127.0.0.1:8090";

const authPayloadSchema = z.object({
  token: z.string().trim().min(1, "Control plane token is required."),
});

async function verifyControlPlaneToken(token: string): Promise<boolean> {
  const response = await fetch(
    `${CONTROL_PLANE_BASE_URL.replace(/\/$/, "")}/api/control-plane/onboarding/status`,
    {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
      },
      cache: "no-store",
    },
  );
  return response.ok;
}

export async function POST(request: NextRequest) {
  try {
    const payload = parseSchemaOrThrow(
      authPayloadSchema,
      await request.json().catch(() => ({})),
      "Invalid operator token payload.",
    );
    const token = payload.token.trim();
    const verified = await verifyControlPlaneToken(token);
    if (!verified) {
      return NextResponse.json(
        { error: "Invalid control plane token." },
        { status: 401, headers: { "Cache-Control": "no-store" } },
      );
    }

    const response = NextResponse.json(
      { ok: true },
      { headers: { "Cache-Control": "no-store" } },
    );
    setWebOperatorSessionCookie(response, token);
    return response;
  } catch (error) {
    return jsonErrorResponse(error, "Unable to establish operator session.");
  }
}

export async function DELETE() {
  const response = NextResponse.json(
    { ok: true },
    { headers: { "Cache-Control": "no-store" } },
  );
  clearWebOperatorSessionCookie(response);
  return response;
}
