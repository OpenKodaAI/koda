import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  return NextResponse.json(
    {
      error:
        "Per-agent schedules are not exposed by the canonical control-plane/runtime APIs",
    },
    { status: 501 },
  );
}
