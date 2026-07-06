import { NextRequest, NextResponse } from "next/server";
import { getOperationalSessions } from "@/lib/runtime-dashboard";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ agentId: string }> },
) {
  const { agentId } = await params;
  const limit = Number(request.nextUrl.searchParams.get("limit") || "100");
  const search = request.nextUrl.searchParams.get("search");

  try {
    const payload = await getOperationalSessions(agentId, {
      limit: Number.isFinite(limit) ? limit : 100,
      search,
    });
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : "Unable to load runtime sessions",
      },
      { status: 500 },
    );
  }
}
