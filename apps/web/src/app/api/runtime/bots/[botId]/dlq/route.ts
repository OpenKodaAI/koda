import { NextRequest, NextResponse } from "next/server";
import { getOperationalDlq } from "@/lib/runtime-dashboard";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ botId: string }> },
) {
  const { botId } = await params;
  const limit = Number(request.nextUrl.searchParams.get("limit") || "100");
  const retryEligibleRaw = request.nextUrl.searchParams.get("retryEligible");
  const retryEligible =
    retryEligibleRaw == null
      ? null
      : retryEligibleRaw.trim().toLowerCase() === "true";

  try {
    const payload = await getOperationalDlq(botId, {
      limit: Number.isFinite(limit) ? limit : 100,
      retryEligible,
    });
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : "Unable to load runtime failures",
      },
      { status: 500 },
    );
  }
}
