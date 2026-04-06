import { NextRequest, NextResponse } from "next/server";
import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import { botIdSchema } from "@/lib/contracts/common";
import { patchScheduleBodySchema } from "@/lib/contracts/schedules";
import { ValidationError } from "@/lib/errors";
import { runtimeFetch, runtimeFetchJson, RuntimeRequestError } from "@/lib/runtime-api";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ botId: string; jobId: string }> }
) {
  let botId: string;
  let jobId: string;

  try {
    const resolved = await params;
    botId = parseSchemaOrThrow(botIdSchema, resolved.botId, "Invalid bot id.");
    jobId = String(Number.parseInt(resolved.jobId, 10));
    if (!jobId || Number.isNaN(Number(jobId))) {
      throw new Error("invalid job id");
    }
  } catch (error) {
    return jsonErrorResponse(error, "Invalid schedule detail request.");
  }

  const response = await runtimeFetchJson<Record<string, unknown>>(
    botId,
    `/api/runtime/schedules/${jobId}`,
    { method: "GET" },
    undefined,
    { capability: "read" }
  );

  if (!response.ok) {
    return NextResponse.json({ error: response.error || "Unable to load schedule" }, { status: response.status });
  }

  return NextResponse.json(response.data);
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ botId: string; jobId: string }> }
) {
  let botId: string;
  let jobId: string;

  try {
    const resolved = await params;
    botId = parseSchemaOrThrow(botIdSchema, resolved.botId, "Invalid bot id.");
    jobId = String(Number.parseInt(resolved.jobId, 10));
    if (!jobId || Number.isNaN(Number(jobId))) {
      throw new Error("invalid job id");
    }
  } catch (error) {
    return jsonErrorResponse(error, "Invalid schedule update request.");
  }

  try {
    const rawBody = await request.text();
    let body = rawBody;
    if (rawBody) {
      let parsed: unknown;
      try {
        parsed = JSON.parse(rawBody);
      } catch {
        return jsonErrorResponse(
          new ValidationError("Request body is not valid JSON."),
          "Invalid schedule update data.",
        );
      }
      try {
        const validated = parseSchemaOrThrow(patchScheduleBodySchema, parsed, "Invalid schedule update data.");
        body = JSON.stringify(validated);
      } catch (error) {
        return jsonErrorResponse(error, "Invalid schedule update data.");
      }
    }
    const upstream = await runtimeFetch(
      botId,
      `/api/runtime/schedules/${jobId}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body,
      },
      undefined,
      { capability: "mutate" }
    );
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") || "application/json" },
    });
  } catch (error) {
    if (error instanceof RuntimeRequestError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    return jsonErrorResponse(error, "Unable to update schedule");
  }
}
