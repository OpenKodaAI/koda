import { NextResponse } from "next/server";
import { z } from "zod";
import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import { SUPPORTED_CHANNELS, checkChannel } from "@/lib/channel-validators";

const channelValidateBodySchema = z.object({
  credentials: z.record(z.string(), z.string().trim().max(2000)).default({}),
});

export async function POST(
  request: Request,
  { params }: { params: Promise<{ agentId: string; channelType: string }> },
) {
  const { channelType } = await params;
  const channel = channelType.toLowerCase();

  if (!SUPPORTED_CHANNELS.has(channel)) {
    return NextResponse.json(
      { ok: false, error: `Unsupported channel type: ${channelType}` },
      { status: 400 },
    );
  }

  let credentials: Record<string, string>;
  try {
    const body = await request.json().catch(() => ({}));
    const validated = parseSchemaOrThrow(
      channelValidateBodySchema,
      body,
      "Invalid request body.",
    );
    credentials = validated.credentials;
  } catch (error) {
    return jsonErrorResponse(error, "Invalid request body.");
  }

  try {
    const result = await checkChannel(channel, credentials);

    if (!result.ok) {
      return NextResponse.json(result, { status: 400 });
    }

    return NextResponse.json(result);
  } catch {
    return NextResponse.json(
      { ok: false, error: `Failed to reach ${channel} API` },
      { status: 502 },
    );
  }
}
