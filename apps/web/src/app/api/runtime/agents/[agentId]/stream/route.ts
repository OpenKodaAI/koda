import { relayRuntimeEventStream } from "@/lib/runtime-stream-relay";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ agentId: string }> }
) {
  const { agentId } = await params;
  const searchParams = new URLSearchParams(new URL(request.url).searchParams);
  return relayRuntimeEventStream(agentId, searchParams);
}
