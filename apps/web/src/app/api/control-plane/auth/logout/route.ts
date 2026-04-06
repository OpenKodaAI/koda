import { NextRequest, NextResponse } from "next/server";

import { clearWebOperatorSessionCookie, getWebOperatorTokenFromCookie } from "@/lib/web-operator-session";
import { isTrustedDashboardRequest } from "@/lib/request-origin";

const CONTROL_PLANE_BASE_URL =
  process.env.CONTROL_PLANE_BASE_URL || "http://127.0.0.1:8090";

export async function POST(request: NextRequest) {
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
  const token = await getWebOperatorTokenFromCookie();
  if (token) {
    await fetch(
      `${CONTROL_PLANE_BASE_URL.replace(/\/$/, "")}/api/control-plane/auth/logout`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      },
    ).catch(() => null);
  }
  clearWebOperatorSessionCookie(response);
  return response;
}
