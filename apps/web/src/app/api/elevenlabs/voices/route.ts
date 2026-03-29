import { NextRequest } from "next/server";
import { createHash } from "crypto";
import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import { optionalLanguageFilterSchema } from "@/lib/contracts/common";
import { controlPlaneFetchJson } from "@/lib/control-plane";
import type { GeneralSystemSettings, ElevenLabsVoiceCatalog, ElevenLabsVoiceOption } from "@/lib/control-plane";

export const dynamic = "force-dynamic";

// ---------------------------------------------------------------------------
// Server-side in-memory cache (1 hour TTL, keyed by API key hash)
// ---------------------------------------------------------------------------

type CacheEntry = {
  data: ElevenLabsVoiceCatalog;
  expiresAt: number;
};

const voiceCache = new Map<string, CacheEntry>();
const CACHE_TTL = 60 * 60 * 1000; // 1 hour

function hashKey(apiKey: string): string {
  return createHash("sha256").update(apiKey).digest("hex").slice(0, 12);
}

function getCached(key: string): ElevenLabsVoiceCatalog | null {
  const entry = voiceCache.get(key);
  if (entry && Date.now() < entry.expiresAt) return entry.data;
  voiceCache.delete(key);
  return null;
}

function setCache(key: string, data: ElevenLabsVoiceCatalog): void {
  voiceCache.set(key, { data, expiresAt: Date.now() + CACHE_TTL });
}

// ---------------------------------------------------------------------------
// ElevenLabs API types
// ---------------------------------------------------------------------------

type ElevenLabsAPIVoice = {
  voice_id: string;
  name: string;
  category: string;
  labels: Record<string, string>;
  preview_url: string;
  fine_tuning?: Record<string, unknown>;
  settings?: Record<string, unknown>;
};

type ElevenLabsAPIResponse = {
  voices: ElevenLabsAPIVoice[];
};

// ---------------------------------------------------------------------------
// Helper: get ElevenLabs API key from control plane settings
// ---------------------------------------------------------------------------

async function getElevenLabsApiKey(): Promise<string | null> {
  try {
    const settings = await controlPlaneFetchJson<GeneralSystemSettings>(
      "/api/control-plane/system-settings/general",
      {},
      { tier: "catalog" },
    );
    if (!settings) return null;
    const conn = settings.values.provider_connections?.elevenlabs;
    if (!conn?.configured && !conn?.verified) return null;
    // The API key is not directly exposed in provider_connections for security.
    // We need to use the control plane's provider endpoint to fetch voices with
    // the stored key. Instead, let's check integration_credentials.
    const creds = settings.values.integration_credentials?.elevenlabs;
    if (creds) {
      const keyField = creds.fields.find(
        (f) => f.key === "api_key" || f.key === "elevenlabs_api_key",
      );
      if (keyField?.value) return keyField.value;
    }
    return null;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Fallback: proxy through control plane (existing behavior)
// ---------------------------------------------------------------------------

async function fetchViaControlPlane(
  language: string,
): Promise<ElevenLabsVoiceCatalog> {
  const query = language ? `?language=${encodeURIComponent(language)}` : "";
  return controlPlaneFetchJson<ElevenLabsVoiceCatalog>(
    `/api/control-plane/providers/elevenlabs/voices${query}`,
    {},
    { tier: "live" },
  );
}

// ---------------------------------------------------------------------------
// Direct ElevenLabs API fetch
// ---------------------------------------------------------------------------

async function fetchFromElevenLabs(
  apiKey: string,
  language: string,
): Promise<ElevenLabsVoiceCatalog> {
  const cacheKey = `elevenlabs:voices:${hashKey(apiKey)}`;
  const cached = getCached(cacheKey);

  let allVoices: ElevenLabsVoiceOption[];
  let allLanguages: Array<{ code: string; label: string }>;
  let fromCache = false;

  if (cached) {
    allVoices = cached.items;
    allLanguages = cached.available_languages;
    fromCache = true;
  } else {
    const res = await fetch("https://api.elevenlabs.io/v1/voices", {
      headers: { "xi-api-key": apiKey },
    });

    if (!res.ok) {
      throw new Error(`ElevenLabs API error: ${res.status} ${res.statusText}`);
    }

    const data: ElevenLabsAPIResponse = await res.json();

    // Transform to our internal format
    const languageSet = new Map<string, string>();
    allVoices = data.voices.map((v) => {
      const voiceLanguages: Array<{ code: string; label: string }> = [];
      // Extract language info from labels
      if (v.labels?.language) {
        const code = v.labels.language.toLowerCase();
        const label = v.labels.language;
        voiceLanguages.push({ code, label });
        if (!languageSet.has(code)) languageSet.set(code, label);
      }
      if (v.labels?.accent) {
        const accentLower = v.labels.accent.toLowerCase();
        if (!languageSet.has(accentLower) && accentLower !== v.labels?.language?.toLowerCase()) {
          // Don't duplicate language from accent
        }
      }

      return {
        voice_id: v.voice_id,
        name: v.name,
        gender: v.labels?.gender ?? "",
        accent: v.labels?.accent ?? "",
        category: v.category ?? "premade",
        preview_url: v.preview_url ?? "",
        languages: voiceLanguages,
      };
    });

    allLanguages = Array.from(languageSet.entries())
      .map(([code, label]) => ({ code, label }))
      .sort((a, b) => a.label.localeCompare(b.label));

    // Cache the full unfiltered result
    const fullCatalog: ElevenLabsVoiceCatalog = {
      items: allVoices,
      available_languages: allLanguages,
      selected_language: "",
      cached: false,
      provider_connected: true,
    };
    setCache(cacheKey, fullCatalog);
  }

  // Filter by language if requested
  let filteredVoices = allVoices;
  if (language) {
    const langLower = language.toLowerCase();
    filteredVoices = allVoices.filter((v) =>
      v.languages.some((l) => l.code.toLowerCase() === langLower) ||
      v.accent.toLowerCase().includes(langLower),
    );
  }

  return {
    items: filteredVoices,
    available_languages: allLanguages,
    selected_language: language,
    cached: fromCache,
    provider_connected: true,
  };
}

// ---------------------------------------------------------------------------
// Route handler
// ---------------------------------------------------------------------------

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
    // Try direct ElevenLabs API first
    const apiKey = await getElevenLabsApiKey();

    if (apiKey) {
      const catalog = await fetchFromElevenLabs(apiKey, language);
      return Response.json(catalog, {
        headers: { "Cache-Control": "private, max-age=300" },
      });
    }

    // Fallback to control plane proxy
    const catalog = await fetchViaControlPlane(language);
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
