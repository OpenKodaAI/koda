import "server-only";

import { NextResponse } from "next/server";
import { runtimeFetch, RuntimeRequestError } from "@/lib/runtime-api";
import { isRejectedStreamStatus, SSE_RESPONSE_HEADERS, streamErrorResponse } from "@/lib/sse";

const STREAM_TIMEOUT_MS = 15 * 60_000;

/**
 * Relay the runtime event stream (`/api/runtime/stream`) to a browser EventSource.
 *
 * - An open upstream stream is piped through.
 * - A request the runtime rejected (400/404/422) becomes one `stream_error`
 *   event on a 200 event stream, so the client can slow down its retries.
 * - Any other failure is transient. It is answered with a non-200 JSON error,
 *   so the EventSource fails without opening and the client keeps its normal
 *   reconnect backoff. This includes everything raised before the runtime
 *   answered: `requireRuntimeAgentConfig` reports any control-plane failure as
 *   "Agent not found", so that 404 does not mean the agent is gone.
 */
export async function relayRuntimeEventStream(
  agentId: string,
  searchParams: URLSearchParams,
): Promise<Response> {
  let upstream: Response;
  try {
    upstream = await runtimeFetch(
      agentId,
      "/api/runtime/stream",
      {
        headers: { Accept: "text/event-stream" },
        timeoutMs: STREAM_TIMEOUT_MS,
      },
      searchParams,
    );
  } catch (error) {
    const status = error instanceof RuntimeRequestError ? error.status : 500;
    const message = error instanceof Error ? error.message : "Unable to proxy runtime stream";
    return NextResponse.json({ error: message }, { status });
  }

  if (upstream.ok && upstream.body) {
    return new Response(upstream.body, {
      status: upstream.status,
      headers: SSE_RESPONSE_HEADERS,
    });
  }

  const text = await upstream.text().catch(() => "");
  if (isRejectedStreamStatus(upstream.status)) {
    return streamErrorResponse(upstream.status);
  }
  return NextResponse.json(
    { error: text || `Unable to open runtime stream (${upstream.status})` },
    { status: upstream.ok ? 502 : upstream.status },
  );
}
