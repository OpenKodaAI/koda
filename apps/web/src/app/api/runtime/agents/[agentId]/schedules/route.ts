import { NextRequest, NextResponse } from "next/server";
import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import { agentIdSchema } from "@/lib/contracts/common";
import { createScheduleBodySchema } from "@/lib/contracts/schedules";
import { runtimeFetchJson } from "@/lib/runtime-api";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ agentId: string }> }
) {
  let agentId: string;

  try {
    agentId = parseSchemaOrThrow(agentIdSchema, (await params).agentId, "Invalid agent id.");
  } catch (error) {
    return jsonErrorResponse(error, "Invalid schedules request.");
  }

  const searchParams = new URLSearchParams(request.nextUrl.searchParams.toString());
  const response = await runtimeFetchJson<{ items?: unknown[] }>(
    agentId,
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

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ agentId: string }> }
) {
  let agentId: string;

  try {
    agentId = parseSchemaOrThrow(agentIdSchema, (await params).agentId, "Invalid agent id.");
  } catch (error) {
    return jsonErrorResponse(error, "Invalid schedules request.");
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON payload." }, { status: 400 });
  }

  let parsed;
  try {
    parsed = parseSchemaOrThrow(createScheduleBodySchema, body, "Invalid routine payload.");
  } catch (error) {
    return jsonErrorResponse(error, "Invalid routine payload.");
  }

  const idempotencyKey = request.headers.get("X-Idempotency-Key") ?? "";

  const response = await runtimeFetchJson<Record<string, unknown>>(
    agentId,
    "/api/runtime/schedules",
    {
      method: "POST",
      body: JSON.stringify(parsed),
      headers: idempotencyKey ? { "X-Idempotency-Key": idempotencyKey } : undefined,
    },
    undefined,
    { capability: "mutate" },
  );

  if (!response.ok) {
    return NextResponse.json(
      { error: response.error || "Unable to create routine" },
      { status: response.status || 500 },
    );
  }

  return NextResponse.json(response.data ?? { ok: true });
}
