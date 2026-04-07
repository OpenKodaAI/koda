import { NextRequest, NextResponse } from "next/server";
import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import { botIdSchema } from "@/lib/contracts/common";
import { runtimeFetchJson } from "@/lib/runtime-api";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ botId: string }> }
) {
  let botId: string;

  try {
    botId = parseSchemaOrThrow(botIdSchema, (await params).botId, "Invalid bot id.");
  } catch (error) {
    return jsonErrorResponse(error, "Invalid schedules request.");
  }

  const searchParams = new URLSearchParams(request.nextUrl.searchParams.toString());
  const response = await runtimeFetchJson<{ items?: unknown[] }>(
    botId,
    "/api/runtime/schedules",
    { method: "GET" },
    searchParams,
    { capability: "read" }
  );

  if (!response.ok) {
    return NextResponse.json({ error: response.error || "Unable to load schedules" }, { status: response.status });
  }

  return NextResponse.json(response.data);
}
