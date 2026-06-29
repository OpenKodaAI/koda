import { NextRequest, NextResponse } from "next/server";
import { getOperationalAgentTasks } from "@/lib/runtime-dashboard";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ agentId: string }> },
) {
  const { agentId } = await params;
  const limit = Number(request.nextUrl.searchParams.get("limit") || "50");
  const search = request.nextUrl.searchParams.get("search");
  const status = request.nextUrl.searchParams.get("status");

  try {
    const payload = await getOperationalAgentTasks(agentId, {
      limit: Number.isFinite(limit) ? limit : 50,
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
            : "Unable to load runtime tasks",
      },
      { status: 500 },
    );
  }
}
