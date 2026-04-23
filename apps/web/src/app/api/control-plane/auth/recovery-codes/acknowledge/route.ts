import { NextRequest, NextResponse } from "next/server";

import { isTrustedDashboardRequest } from "@/lib/request-origin";
import { clearPendingRecoveryCookie } from "@/lib/web-operator-session";

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
  clearPendingRecoveryCookie(response);
  return response;
}
