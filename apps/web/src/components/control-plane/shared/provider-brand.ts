/* -------------------------------------------------------------------------- */
/*  Provider branding — single source of truth for logos, colors, and icons  */
/*                                                                            */
/*  Every UI surface that displays a model badge (agent editor, model         */
/*  selector, system settings, integrations grid) reads from this module so   */
/*  the brand treatment never drifts between routes.                          */
/* -------------------------------------------------------------------------- */

import { Cpu } from "lucide-react";
import type { ComponentType, SVGProps } from "react";

/** Logo asset path per provider. Logos live under apps/web/public/providers/. */
export const PROVIDER_LOGOS: Record<string, string> = {
  claude: "/providers/anthropic.svg",
  codex: "/providers/openai.svg",
  gemini: "/providers/google.svg",
  elevenlabs: "/providers/elevenlabs.svg",
  ollama: "/providers/ollama.svg",
  perplexity: "/providers/perplexity.svg",
  mistral: "/providers/mistral.svg",
  qwen: "/providers/qwen.svg",
  kimi: "/providers/kimi.svg",
  groq: "/providers/groq.svg",
  deepseek: "/providers/deepseek.svg",
  xai: "/providers/xai.svg",
};

/**
 * Lucide icons used in place of an asset logo. Local-runtime providers that
 * don't have a vendor logo (Kokoro) get a CPU glyph so operators recognize
 * them as on-device compute. Ollama keeps its own logo so models served by
 * an Ollama endpoint (qwen3, gemma3, deepseek-r1, etc.) are visually badged
 * as Ollama, not as the underlying open-source model.
 */
export const PROVIDER_ICON_COMPONENTS: Record<string, ComponentType<SVGProps<SVGSVGElement>>> = {
  kokoro: Cpu,
};

/**
 * Brand accent colors as `R G B` triplets, consumable via `rgba(${accent}, X)`.
 * Sourced from each vendor's official brand guidelines / marketing surfaces.
 * Local-runtime providers use neutral grey so they read as "system" rather
 * than competing with the cloud provider palette.
 */
export const PROVIDER_ACCENTS: Record<string, string> = {
  claude: "212 164 128", // Anthropic peach
  codex: "16 163 127", // OpenAI green
  gemini: "86 138 248", // Google blue
  elevenlabs: "250 204 21", // ElevenLabs yellow
  ollama: "56 189 248", // Ollama brand light blue
  kokoro: "148 152 160", // Local-runtime neutral grey
  perplexity: "32 178 170", // Perplexity teal
  mistral: "255 95 0", // Mistral hot orange
  qwen: "97 84 219", // Qwen purple
  kimi: "0 113 208", // Moonshot blue
  groq: "242 87 53", // Groq orange-red
  deepseek: "76 99 230", // DeepSeek blue
  xai: "230 230 230", // xAI near-white
};

/**
 * Logos that ship with a single fill (no brand palette) — rendered via
 * mask-image so the glyph adapts to the active theme/accent color.
 */
export const MONOCHROME_LOGO_PROVIDERS: ReadonlySet<string> = new Set([
  "codex",
  "elevenlabs",
  "ollama",
  "groq",
  "xai",
]);

/**
 * Logos with a colored brand palette. Rendered as a real <img> so the
 * original colors show through even when the surrounding card is active or
 * accented — the alternative (mask-tint) flattens them to a single hue.
 */
export const COLORED_BRAND_LOGO_PROVIDERS: ReadonlySet<string> = new Set([
  "perplexity",
  "mistral",
  "qwen",
  "kimi",
  "deepseek",
]);

/**
 * Logos that should mask-tint by default (not just when the card is active).
 * Used for vendor logos whose default rendering is too contrasty against the
 * dark canvas, e.g. Gemini's blue-on-white badge.
 */
export const MASKED_LOGO_PROVIDERS: ReadonlySet<string> = new Set(["gemini"]);

/**
 * Local-only providers — the agent editor surfaces a "local" hint and uses
 * the neutral grey accent so operators immediately recognize on-device
 * inference without parsing the model ID.
 */
export const LOCAL_RUNTIME_PROVIDERS: ReadonlySet<string> = new Set([
  "kokoro",
]);

export function isLocalRuntimeProvider(providerId: string): boolean {
  return LOCAL_RUNTIME_PROVIDERS.has(providerId);
}

/**
 * Resolves the glyph color for a provider's logo. Monochrome glyphs follow
 * the theme's primary text color so they're legible on every canvas; colored
 * brand logos return their accent only when the surrounding card is active.
 */
export function providerGlyphColor(providerId: string, emphasized = false): string {
  if (MONOCHROME_LOGO_PROVIDERS.has(providerId)) {
    return "var(--text-primary)";
  }
  if (!emphasized) {
    return "var(--text-primary)";
  }
  const accent = PROVIDER_ACCENTS[providerId] ?? "255 255 255";
  return `rgb(${accent})`;
}

/** Display name shown in dropdowns / labels. */
export const PROVIDER_DISPLAY_NAMES: Record<string, string> = {
  claude: "Anthropic",
  codex: "OpenAI",
  gemini: "Google",
  ollama: "Ollama",
  kokoro: "Kokoro (local)",
  perplexity: "Perplexity",
  mistral: "Mistral",
  qwen: "Qwen",
  kimi: "Kimi",
  groq: "Groq",
  deepseek: "DeepSeek",
  xai: "xAI",
  elevenlabs: "ElevenLabs",
};

export function providerDisplayName(providerId: string): string {
  return PROVIDER_DISPLAY_NAMES[providerId] ?? providerId;
}
