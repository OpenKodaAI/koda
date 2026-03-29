import { NextResponse } from "next/server";
import { getOperationalSessionDetail } from "@/lib/runtime-dashboard";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  _request: Request,
  {
    params,
  }: {
    params: Promise<{ botId: string; sessionId: string }>;
  },
) {
  const { botId, sessionId } = await params;

  try {
    const payload = await getOperationalSessionDetail(botId, sessionId);
    return NextResponse.json(payload);
  } catch (error) {
    const status =
      error instanceof Error && error.message === "Session not found" ? 404 : 500;
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : "Unable to load runtime session detail",
      },
      { status },
    );
  }
}
