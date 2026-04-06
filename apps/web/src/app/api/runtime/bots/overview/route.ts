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

  const botsParam = request.nextUrl.searchParams.get("bots") ?? "";
  const botIds = botsParam
    .split(",")
    .map((id) => id.trim())
    .filter((id) => id.length > 0 && id.length <= 120 && BOT_ID_PATTERN.test(id));

  if (botIds.length === 0) {
    return NextResponse.json({});
  }

  const uniqueBotIds = [...new Set(botIds)].slice(0, MAX_BOTS_PER_REQUEST);

  const results = await Promise.allSettled(
    uniqueBotIds.map(async (botId) => {
      const overview = await getRuntimeOverview(botId, language);
      return [botId, overview] as const;
    }),
  );

  const payload: Record<string, RuntimeOverview> = {};
  for (const result of results) {
    if (result.status === "fulfilled") {
      const [botId, overview] = result.value;
      payload[botId] = overview;
    }
  }

  return NextResponse.json(payload);
}
