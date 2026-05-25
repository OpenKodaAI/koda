import { NextRequest, NextResponse } from "next/server";
import { getOperationalCostInsights } from "@/lib/runtime-dashboard";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  const agentIds = request.nextUrl.searchParams.getAll("agent").filter(Boolean);
  const period = request.nextUrl.searchParams.get("period");
  const model = request.nextUrl.searchParams.get("model");
  const taskType = request.nextUrl.searchParams.get("taskType");

  try {
    const payload = await getOperationalCostInsights({
      agentIds,
      period,
      model,
      taskType,
    });
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : "Unable to load runtime costs",
      },
      { status: 500 },
    );
  }
}
