import { NextRequest } from "next/server";
import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import { optionalLanguageFilterSchema } from "@/lib/contracts/common";
import { controlPlaneFetchJson } from "@/lib/control-plane";
import type { ElevenLabsVoiceCatalog } from "@/lib/control-plane";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  let language = "";

  try {
    language = parseSchemaOrThrow(
      optionalLanguageFilterSchema,
      request.nextUrl.searchParams.get("language") ?? "",
    );
  } catch (error) {
    return jsonErrorResponse(error, "Invalid ElevenLabs request.");
  }

  try {
    const query = language ? `?language=${encodeURIComponent(language)}` : "";
    const catalog = await controlPlaneFetchJson<ElevenLabsVoiceCatalog>(
      `/api/control-plane/providers/elevenlabs/voices${query}`,
      {},
      { tier: "live" },
    );
    return Response.json(catalog, {
      headers: { "Cache-Control": "private, max-age=60" },
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to fetch voices";
    return Response.json(
      {
        items: [],
        available_languages: [],
        selected_language: language,
        cached: false,
        provider_connected: false,
        error: message,
      } satisfies ElevenLabsVoiceCatalog & { error: string },
      { status: 502 },
    );
  }
}
