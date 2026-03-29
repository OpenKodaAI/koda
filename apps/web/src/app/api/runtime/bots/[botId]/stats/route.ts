import { NextResponse } from "next/server";
import { getOperationalBotStats } from "@/lib/runtime-dashboard";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ botId: string }> },
) {
  const { botId } = await params;

  try {
    const payload = await getOperationalBotStats(botId);
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : "Unable to load runtime bot stats",
      },
      { status: 500 },
    );
  }
}
