import { NextRequest, NextResponse } from "next/server";
import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import { agentIdSchema } from "@/lib/contracts/common";
import { runtimeFetchJson } from "@/lib/runtime-api";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Validates a schedule and previews its next runs, as the scheduler computes them (D-080). */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ agentId: string }> }
) {
  let agentId: string;
  try {
    agentId = parseSchemaOrThrow(agentIdSchema, (await params).agentId, "Invalid agent id.");
  } catch (error) {
    return jsonErrorResponse(error, "Invalid schedule preview request.");
  }

  const search = new URLSearchParams();
  for (const key of ["trigger_type", "schedule_expr", "timezone"]) {
    search.set(key, (request.nextUrl.searchParams.get(key) ?? "").slice(0, 120));
  }
  const response = await runtimeFetchJson<Record<string, unknown>>(
    agentId,
    "/api/runtime/schedules/preview",
    { method: "GET" },
    search,
    { capability: "read" }
  );

  if (!response.ok) {
    return NextResponse.json(
      { error: response.error || "Unable to preview schedule" },
      { status: response.status }
    );
  }
  return NextResponse.json(response.data);
}
