import { NextResponse } from "next/server";

import { getWebOperatorTokenFromCookie } from "@/lib/web-operator-session";

const CONTROL_PLANE_BASE_URL = process.env.CONTROL_PLANE_BASE_URL || "http://127.0.0.1:8090";

export async function GET() {
  const token = await getWebOperatorTokenFromCookie();
  if (!token) {
    return NextResponse.json(
      { error: "Operator session is required." },
      { status: 401, headers: { "Cache-Control": "no-store" } },
    );
  }
  const upstream = await fetch(
    `${CONTROL_PLANE_BASE_URL.replace(/\/$/, "")}/api/control-plane/auth/recovery-codes`,
    {
      method: "GET",
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    },
  );
  const data = (await upstream.json().catch(() => ({}))) as Record<string, unknown>;
  if (!upstream.ok) {
    return NextResponse.json(
      { error: String(data.error || "Unable to load recovery codes.") },
      { status: upstream.status || 400, headers: { "Cache-Control": "no-store" } },
    );
  }
  return NextResponse.json(data, { headers: { "Cache-Control": "no-store" } });
}
