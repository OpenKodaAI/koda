import { NextRequest } from "next/server";
import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import { optionalLanguageFilterSchema } from "@/lib/contracts/common";
import { controlPlaneFetchJson } from "@/lib/control-plane";
import type { ElevenLabsVoiceCatalog } from "@/lib/control-plane";

export const dynamic = "force-dynamic";

function normalizeVoiceCatalog(
  payload: ElevenLabsVoiceCatalog | null,
  selectedLanguage: string,
): ElevenLabsVoiceCatalog {
  if (!payload || typeof payload !== "object") {
    return {
      items: [],
      available_languages: [],
      selected_language: selectedLanguage,
      cached: false,
      provider_connected: false,
    };
  }

  return {
    ...payload,
    items: Array.isArray(payload.items) ? payload.items : [],
    available_languages: Array.isArray(payload.available_languages)
      ? payload.available_languages
      : [],
    selected_language: String(payload.selected_language ?? selectedLanguage),
    cached: Boolean(payload.cached),
    provider_connected: Boolean(payload.provider_connected),
  };
}

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
    const catalog = await controlPlaneFetchJson<ElevenLabsVoiceCatalog | null>(
      `/api/control-plane/providers/elevenlabs/voices${query}`,
      {},
      { tier: "live" },
    );
    return Response.json(normalizeVoiceCatalog(catalog, language), {
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
