import { NextResponse } from "next/server";
import { getOperationalExecutionDetail } from "@/lib/runtime-dashboard";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ botId: string; taskId: string }> },
) {
  const { botId, taskId } = await params;
  const numericTaskId = Number(taskId);

  if (!Number.isFinite(numericTaskId)) {
    return NextResponse.json({ error: "Invalid task id" }, { status: 400 });
  }

  try {
    const payload = await getOperationalExecutionDetail(botId, numericTaskId);
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : "Unable to load runtime execution detail",
      },
      { status: 500 },
    );
  }
}
