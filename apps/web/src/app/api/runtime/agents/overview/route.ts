import { NextRequest, NextResponse } from "next/server";
import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import { languageSchema } from "@/lib/contracts/common";
import { LOCALE_COOKIE_KEY } from "@/lib/i18n";
import { getRuntimeOverview } from "@/lib/runtime-api";
import type { RuntimeOverview } from "@/lib/runtime-types";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const BOT_ID_PATTERN = /^[A-Za-z0-9:_-]+$/;
const MAX_BOTS_PER_REQUEST = 50;

export async function GET(request: NextRequest) {
  let language: string;

  try {
    language = parseSchemaOrThrow(
      languageSchema,
      request.nextUrl.searchParams.get("lang") ?? request.cookies.get(LOCALE_COOKIE_KEY)?.value,
    );
  } catch (error) {
    return jsonErrorResponse(error, "Invalid batch overview request.");
  }

  const botsParam = request.nextUrl.searchParams.get("agents") ?? "";
  const agentIds = botsParam
    .split(",")
    .map((id) => id.trim())
    .filter((id) => id.length > 0 && id.length <= 120 && BOT_ID_PATTERN.test(id));

  if (agentIds.length === 0) {
    return NextResponse.json({});
  }

  const uniqueBotIds = [...new Set(agentIds)].slice(0, MAX_BOTS_PER_REQUEST);

  const results = await Promise.allSettled(
    uniqueBotIds.map(async (agentId) => {
      const overview = await getRuntimeOverview(agentId, language);
      return [agentId, overview] as const;
    }),
  );

  const payload: Record<string, RuntimeOverview> = {};
  for (const result of results) {
    if (result.status === "fulfilled") {
      const [agentId, overview] = result.value;
      payload[agentId] = overview;
    }
  }

  return NextResponse.json(payload);
}
