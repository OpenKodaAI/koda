import { NextResponse } from "next/server";
import { runtimeFetch, RuntimeRequestError } from "@/lib/runtime-api";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const VALID_ACTIONS = new Set(["cancel", "pause", "resume"]);

export async function POST(
  request: Request,
  {
    params,
  }: { params: Promise<{ agentId: string; sessionId: string; action: string }> },
) {
  const { agentId, sessionId, action } = await params;
  if (!VALID_ACTIONS.has(action)) {
    return NextResponse.json({ error: "invalid action" }, { status: 400 });
  }

  const searchParams = new URLSearchParams(new URL(request.url).searchParams);

  try {
    const upstream = await runtimeFetch(
      agentId,
      `/api/runtime/sessions/${encodeURIComponent(sessionId)}/${action}`,
      {
        method: "POST",
      },
      searchParams,
      { capability: "mutate" },
    );

    const contentType = upstream.headers.get("content-type") || "application/json";
    const body = await upstream.text();
    return new Response(body, {
      status: upstream.status,
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    const status = error instanceof RuntimeRequestError ? error.status : 500;
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : `Unable to ${action} session`,
      },
      { status },
    );
  }
}
