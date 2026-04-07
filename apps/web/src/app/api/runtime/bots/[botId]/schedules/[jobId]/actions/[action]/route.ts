import { NextRequest, NextResponse } from "next/server";
import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import { botIdSchema } from "@/lib/contracts/common";
import { scheduleActionBodySchema } from "@/lib/contracts/schedules";
import { ValidationError } from "@/lib/errors";
import { runtimeFetch, RuntimeRequestError } from "@/lib/runtime-api";

const ALLOWED_ACTIONS = ["run", "pause", "resume", "cancel", "validate", "delete"];

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ botId: string; jobId: string; action: string }> }
) {
  let botId: string;
  let jobId: string;
  let action: string;

  try {
    const resolved = await params;
    botId = parseSchemaOrThrow(botIdSchema, resolved.botId, "Invalid bot id.");
    jobId = String(Number.parseInt(resolved.jobId, 10));
    action = String(resolved.action || "").trim().toLowerCase();
    if (!jobId || Number.isNaN(Number(jobId)) || !action) {
      throw new Error("invalid schedule action request");
    }
    if (!ALLOWED_ACTIONS.includes(action)) {
      throw new ValidationError(`Unknown action: ${action}. Allowed: ${ALLOWED_ACTIONS.join(", ")}.`);
    }
  } catch (error) {
    return jsonErrorResponse(error, "Invalid schedule action request.");
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
          "Invalid schedule action data.",
        );
      }
      try {
        const validated = parseSchemaOrThrow(scheduleActionBodySchema, parsed, "Invalid schedule action data.");
        body = JSON.stringify(validated);
      } catch (error) {
        return jsonErrorResponse(error, "Invalid schedule action data.");
      }
    }
    const upstream = await runtimeFetch(
      botId,
      `/api/runtime/schedules/${jobId}/actions/${action}`,
      {
        method: "POST",
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
    return jsonErrorResponse(error, "Unable to run schedule action");
  }
}
