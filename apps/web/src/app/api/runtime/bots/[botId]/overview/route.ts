import { NextRequest, NextResponse } from "next/server";
import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import { botIdSchema, languageSchema } from "@/lib/contracts/common";
import { LOCALE_COOKIE_KEY } from "@/lib/i18n";
import { getRuntimeOverview, RuntimeRequestError } from "@/lib/runtime-api";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ botId: string }> }
) {
  let botId: string;
  let language: string;

  try {
    botId = parseSchemaOrThrow(botIdSchema, (await params).botId, "Invalid bot id.");
    language = parseSchemaOrThrow(
      languageSchema,
      request.nextUrl.searchParams.get("lang") ?? request.cookies.get(LOCALE_COOKIE_KEY)?.value,
    );
  } catch (error) {
    return jsonErrorResponse(error, "Invalid runtime overview request.");
  }

  try {
    const payload = await getRuntimeOverview(botId, language);
    return NextResponse.json(payload);
  } catch (error) {
    if (error instanceof RuntimeRequestError) {
      return NextResponse.json(
        {
          error: error.message,
        },
        { status: error.status },
      );
    }

    return jsonErrorResponse(error, "Unable to load runtime overview");
  }
}
