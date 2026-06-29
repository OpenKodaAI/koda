import { NextResponse } from "next/server";
import { runtimeFetch, RuntimeRequestError } from "@/lib/runtime-api";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ agentId: string }> }
) {
  const { agentId } = await params;
  const url = new URL(request.url);
  const searchParams = new URLSearchParams(url.searchParams);

  try {
    const upstream = await runtimeFetch(
      agentId,
      "/api/runtime/stream",
      {
        headers: {
          Accept: "text/event-stream",
        },
        timeoutMs: 15 * 60_000,
      },
      searchParams
    );

    if (!upstream.ok || !upstream.body) {
      const text = await upstream.text().catch(() => "");
      return NextResponse.json(
        {
          error: text || `Unable to open runtime stream (${upstream.status})`,
        },
        { status: upstream.status }
      );
    }

    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  } catch (error) {
    const status = error instanceof RuntimeRequestError ? error.status : 500;
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Unable to proxy runtime stream",
      },
      { status }
    );
  }
}
