import { NextResponse } from "next/server";
import { getOperationalAgentStats } from "@/lib/runtime-dashboard";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ agentId: string }> },
) {
  const { agentId } = await params;

  try {
    const payload = await getOperationalAgentStats(agentId);
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : "Unable to load runtime agent stats",
      },
      { status: 500 },
    );
  }
}
