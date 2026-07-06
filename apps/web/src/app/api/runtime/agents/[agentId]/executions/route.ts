import { NextRequest, NextResponse } from "next/server";
import { getOperationalExecutions } from "@/lib/runtime-dashboard";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ agentId: string }> },
) {
  const { agentId } = await params;
  const limit = Number(request.nextUrl.searchParams.get("limit") || "100");
  const search = request.nextUrl.searchParams.get("search");
  const status = request.nextUrl.searchParams.get("status");

  try {
    const payload = await getOperationalExecutions(agentId, {
      limit: Number.isFinite(limit) ? limit : 100,
      search,
      status,
    });
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : "Unable to load runtime executions",
      },
      { status: 500 },
    );
  }
}
