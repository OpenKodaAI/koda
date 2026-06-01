import { NextResponse } from "next/server";
import { getOperationalSessionDetail } from "@/lib/runtime-dashboard";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  _request: Request,
  {
    params,
  }: {
    params: Promise<{ agentId: string; sessionId: string }>;
  },
) {
  const { agentId, sessionId } = await params;

  try {
    const payload = await getOperationalSessionDetail(agentId, sessionId);
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
