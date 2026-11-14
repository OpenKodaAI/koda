import { relayRuntimeEventStream } from "@/lib/runtime-stream-relay";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Failures follow `relayRuntimeEventStream`: a transient failure answers with a
// non-200 status, so the EventSource never opens and `useSessionStream` keeps
// growing its reconnect backoff instead of resetting it on every attempt.
export async function GET(
  request: Request,
  {
    params,
  }: { params: Promise<{ agentId: string; sessionId: string }> },
) {
  const { agentId, sessionId } = await params;
  const searchParams = new URLSearchParams(new URL(request.url).searchParams);
  searchParams.set("session_id", sessionId);
  return relayRuntimeEventStream(agentId, searchParams);
}
