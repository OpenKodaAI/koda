import { NextResponse } from "next/server";
import { CHANNEL_SECRET_KEYS, checkChannel, fetchChannelSecrets } from "@/lib/channel-validators";

// ---------------------------------------------------------------------------
//  Route handler
// ---------------------------------------------------------------------------

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ agentId: string; channelType: string }> },
) {
  const { agentId, channelType } = await params;
  const channel = channelType.toLowerCase();

  const secretKeys = CHANNEL_SECRET_KEYS[channel];
  if (!secretKeys) {
    return NextResponse.json(
      { ok: false, error: `Unsupported channel type: ${channelType}` },
      { status: 400 },
    );
  }

  try {
    const credentials = await fetchChannelSecrets(agentId, secretKeys);
    const result = await checkChannel(channel, credentials);

    if (!result.ok) {
      return NextResponse.json(result, { status: 400 });
    }

    return NextResponse.json(result);
  } catch {
    return NextResponse.json(
      { ok: false, error: `Failed to check ${channel} status` },
      { status: 502 },
    );
  }
}
