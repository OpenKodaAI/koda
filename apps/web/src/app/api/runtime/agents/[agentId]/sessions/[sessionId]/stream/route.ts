import { runtimeFetch, RuntimeRequestError } from "@/lib/runtime-api";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function emptySessionStream(message: string) {
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(`: ${message}\nretry: 15000\n\n`));
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}

export async function GET(
  request: Request,
  {
    params,
  }: { params: Promise<{ agentId: string; sessionId: string }> },
) {
  const { agentId, sessionId } = await params;
  const url = new URL(request.url);
  const searchParams = new URLSearchParams(url.searchParams);
  searchParams.set("session_id", sessionId);

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
      searchParams,
    );

    if (!upstream.ok || !upstream.body) {
      await upstream.text().catch(() => "");
      return emptySessionStream(`session stream unavailable (${upstream.status})`);
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
    return emptySessionStream(`session stream unavailable (${status})`);
  }
}
