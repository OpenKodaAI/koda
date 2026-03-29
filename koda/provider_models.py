"""Canonical provider model catalogs grouped by product functionality."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ModelFunctionDefinition:
    id: str
    title: str
    description: str


@dataclass(frozen=True, slots=True)
class ProviderModelDefinition:
    provider_id: str
    model_id: str
    title: str
    function_id: str
    description: str = ""
    status: str = "current"


_MODEL_FUNCTIONS: tuple[ModelFunctionDefinition, ...] = (
    ModelFunctionDefinition("general", "Geral", "Conversas, raciocinio e execucao principal dos agents."),
    ModelFunctionDefinition("image", "Imagem", "Geracao ou edicao de imagem."),
    ModelFunctionDefinition("video", "Video", "Geracao ou transformacao de video."),
    ModelFunctionDefinition("audio", "Audio", "Sintese de fala ou audio generativo."),
    ModelFunctionDefinition("transcription", "Transcricao", "Speech-to-text e transcricao de audio."),
    ModelFunctionDefinition("music", "Musica", "Geracao de musica e trilhas."),
)

MODEL_FUNCTION_IDS: tuple[str, ...] = tuple(item.id for item in _MODEL_FUNCTIONS)

_DYNAMIC_GENERAL_MODEL_LABELS: dict[str, dict[str, str]] = {
    "claude": {
        "claude-3-5-haiku-latest": "Claude 3.5 Haiku",
        "claude-3-7-sonnet-latest": "Claude 3.7 Sonnet",
        "claude-3-7-sonnet-20250219": "Claude 3.7 Sonnet (snapshot)",
        "claude-sonnet-4-20250514": "Claude Sonnet 4",
        "claude-opus-4-1-20250805": "Claude Opus 4.1",
        "claude-haiku-4-5-20251001": "Claude Haiku 4.5",
        "claude-sonnet-4-5": "Claude Sonnet 4.5",
        "claude-sonnet-4-6": "Claude Sonnet 4.6",
        "claude-opus-4-1": "Claude Opus 4.1",
        "claude-opus-4-6": "Claude Opus 4.6",
    },
    "codex": {
        "gpt-5": "GPT-5",
        "gpt-5-mini": "GPT-5 mini",
        "gpt-5-nano": "GPT-5 nano",
        "gpt-5-pro": "GPT-5 Pro",
        "gpt-5.4-pro": "GPT-5.4 Pro",
        "gpt-5.4-mini": "GPT-5.4 mini",
        "gpt-5.4-nano": "GPT-5.4 nano",
        "gpt-5.4": "GPT-5.4",
        "gpt-5.2-pro": "GPT-5.2 Pro",
        "gpt-5.2": "GPT-5.2",
        "gpt-5.2-codex": "GPT-5.2 Codex",
        "gpt-5.1": "GPT-5.1",
        "gpt-5.1-codex": "GPT-5.1 Codex",
        "gpt-5.1-codex-max": "GPT-5.1 Codex Max",
        "gpt-5-codex": "GPT-5 Codex",
        "o3-pro": "o3 Pro",
        "o3": "o3",
        "o3-mini": "o3 mini",
        "o4-mini": "o4 mini",
        "gpt-4.1": "GPT-4.1",
        "gpt-4o": "GPT-4o",
        "gpt-4o-mini": "GPT-4o mini",
        "gpt-4.1-mini": "GPT-4.1 mini",
        "gpt-4.1-nano": "GPT-4.1 nano",
        "gpt-5.3-codex": "GPT-5.3 Codex",
    },
    "gemini": {
        "gemini-2.5-flash-lite": "Gemini 2.5 Flash-Lite",
        "gemini-2.5-flash": "Gemini 2.5 Flash",
        "gemini-2.5-pro": "Gemini 2.5 Pro",
        "gemini-3-flash-preview": "Gemini 3 Flash Preview",
        "gemini-3.1-flash-lite-preview": "Gemini 3.1 Flash-Lite Preview",
        "gemini-3.1-pro-preview": "Gemini 3.1 Pro Preview",
        "gemini-3.0-flash": "Gemini 3.0 Flash (legacy)",
        "gemini-3.0-flash-lite": "Gemini 3.0 Flash-Lite (legacy)",
    },
    "ollama": {
        "gpt-oss:20b": "GPT-OSS 20B",
        "gpt-oss:120b": "GPT-OSS 120B",
        "qwen3:latest": "Qwen 3",
        "qwen3-coder:latest": "Qwen 3 Coder",
        "gemma3:latest": "Gemma 3",
        "llama3.3:latest": "Llama 3.3",
        "llama4:latest": "Llama 4",
        "deepseek-r1:latest": "DeepSeek R1",
        "mistral-small3.1:latest": "Mistral Small 3.1",
        "phi4:latest": "Phi 4",
        "devstral:latest": "Devstral",
    },
}

_STATIC_PROVIDER_MODELS: tuple[ProviderModelDefinition, ...] = (
    ProviderModelDefinition(
        "codex", "gpt-image-1.5", "GPT Image 1.5", "image", "Modelo oficial da OpenAI para imagem."
    ),
    ProviderModelDefinition(
        "codex",
        "sora-2",
        "Sora 2 (visual guiado por imagem)",
        "image",
        "Modelo Sora exposto para fluxos visuais guiados por texto ou imagem de referencia. "
        "A saida oficial do modelo e video.",
        status="preview",
    ),
    ProviderModelDefinition(
        "codex",
        "sora-2-pro",
        "Sora 2 Pro (visual guiado por imagem)",
        "image",
        "Variante premium do Sora para fluxos visuais guiados por imagem. A saida oficial do modelo e video.",
        status="preview",
    ),
    ProviderModelDefinition("codex", "sora-2", "Sora 2", "video", "Modelo de video da OpenAI."),
    ProviderModelDefinition("codex", "sora-2-pro", "Sora 2 Pro", "video", "Versao premium do Sora 2."),
    ProviderModelDefinition(
        "codex", "gpt-audio-1.5", "GPT Audio 1.5", "audio", "Modelo de audio multimodal da OpenAI."
    ),
    ProviderModelDefinition(
        "codex",
        "whisper-1",
        "Whisper API",
        "transcription",
        "Transcricao via OpenAI Whisper API.",
    ),
    ProviderModelDefinition(
        "codex",
        "gpt-4o-transcribe",
        "GPT-4o Transcribe",
        "transcription",
        "Transcricao principal da OpenAI.",
    ),
    ProviderModelDefinition(
        "codex",
        "gpt-4o-mini-transcribe",
        "GPT-4o mini Transcribe",
        "transcription",
        "Transcricao economica da OpenAI.",
    ),
    ProviderModelDefinition(
        "gemini",
        "gemini-2.5-flash-image-preview",
        "Gemini 2.5 Flash Image Preview (Nano Banana 1)",
        "image",
        "Versao preview do Gemini 2.5 Flash Image, popularmente chamada de Nano Banana.",
        status="preview",
    ),
    ProviderModelDefinition(
        "gemini",
        "gemini-2.5-flash-image",
        "Gemini 2.5 Flash Image (Nano Banana)",
        "image",
        "Modelo estavel do Gemini 2.5 Flash Image para geracao e edicao de imagem.",
    ),
    ProviderModelDefinition(
        "gemini",
        "gemini-3-pro-image-preview",
        "Gemini 3 Pro Image Preview (Nano Banana 2)",
        "image",
        "Modelo Gemini 3 Pro Image Preview para geracao e edicao premium de imagem.",
        status="preview",
    ),
    ProviderModelDefinition(
        "gemini",
        "imagen-4.0-generate-001",
        "Imagen 4 Standard",
        "image",
        "Geracao de imagem com Imagen 4.",
    ),
    ProviderModelDefinition(
        "gemini",
        "imagen-4.0-ultra-generate-001",
        "Imagen 4 Ultra",
        "image",
        "Geracao premium de imagem com Imagen 4 Ultra.",
    ),
    ProviderModelDefinition(
        "gemini",
        "veo-3.0-generate-preview",
        "Veo 3",
        "video",
        "Geracao de video com audio.",
        status="preview",
    ),
    ProviderModelDefinition(
        "gemini",
        "veo-3.0-fast-generate-preview",
        "Veo 3 Fast",
        "video",
        "Versao acelerada do Veo 3.",
        status="preview",
    ),
    ProviderModelDefinition(
        "gemini",
        "veo-3.1-generate-preview",
        "Veo 3.1",
        "video",
        "Geracao de video com audio e melhorias de image-to-video no Gemini API.",
        status="preview",
    ),
    ProviderModelDefinition(
        "gemini",
        "veo-3.1-fast-generate-preview",
        "Veo 3.1 Fast",
        "video",
        "Variante acelerada do Veo 3.1 para video com audio e image-to-video.",
        status="preview",
    ),
    ProviderModelDefinition(
        "gemini",
        "gemini-2.5-flash-native-audio-preview-09-2025",
        "Gemini 2.5 Flash Native Audio",
        "audio",
        "Modelo oficial de audio nativo da Gemini.",
        status="preview",
    ),
    ProviderModelDefinition(
        "gemini",
        "lyria-realtime-exp",
        "Lyria Realtime",
        "music",
        "Geracao musical em tempo real.",
        status="experimental",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_v3",
        "Eleven v3",
        "audio",
        "Modelo flagship de TTS da ElevenLabs.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_ttv_v3",
        "Eleven v3 Text to Voice",
        "audio",
        "Voice design da familia Eleven v3.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_multilingual_v2",
        "Eleven Multilingual v2",
        "audio",
        "Modelo multilíngue estavel para TTS.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_flash_v2_5",
        "Eleven Flash v2.5",
        "audio",
        "Modelo rapido e economico para voz.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_flash_v2",
        "Eleven Flash v2",
        "audio",
        "Versao anterior focada em baixa latencia.",
        status="legacy",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_turbo_v2_5",
        "Eleven Turbo v2.5",
        "audio",
        "Modelo turbo para sintese de fala.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_multilingual_sts_v2",
        "Eleven Multilingual STS v2",
        "audio",
        "Speech-to-speech multilíngue.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_multilingual_ttv_v2",
        "Eleven Multilingual TTV v2",
        "audio",
        "Text-to-voice designer multilíngue.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_english_sts_v2",
        "Eleven English STS v2",
        "audio",
        "Speech-to-speech focado em ingles.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_text_to_sound_v2",
        "Eleven Text to Sound v2",
        "audio",
        "Geracao de efeitos sonoros.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_multilingual_v1",
        "Eleven Multilingual v1",
        "audio",
        "Modelo multilíngue anterior.",
        status="deprecated",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "eleven_monolingual_v1",
        "Eleven Monolingual v1",
        "audio",
        "Modelo ingles anterior.",
        status="deprecated",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "scribe_v2",
        "Scribe v2",
        "transcription",
        "Transcricao principal da ElevenLabs.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "scribe_v2_realtime",
        "Scribe v2 Realtime",
        "transcription",
        "Transcricao em tempo real.",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "scribe_v1",
        "Scribe v1",
        "transcription",
        "Transcricao legada da ElevenLabs.",
        status="legacy",
    ),
    ProviderModelDefinition(
        "elevenlabs",
        "music_v1",
        "Eleven Music",
        "music",
        "Geracao musical da ElevenLabs.",
    ),
    ProviderModelDefinition("kokoro", "kokoro-v1", "Kokoro v1", "audio", "Modelo local de TTS."),
    ProviderModelDefinition(
        "whispercpp",
        "whisper-cpp-local",
        "Whisper CPP (local)",
        "transcription",
        "Transcricao local gratuita executada pela API do agent com whisper.cpp.",
    ),
    ProviderModelDefinition("sora", "sora-2", "Sora 2", "video", "Geracao de video da OpenAI."),
    ProviderModelDefinition("sora", "sora-2-pro", "Sora 2 Pro", "video", "Versao premium do Sora 2."),
)


def resolve_model_function_catalog() -> list[dict[str, Any]]:
    return [{"id": item.id, "title": item.title, "description": item.description} for item in _MODEL_FUNCTIONS]


def _general_model_title(provider_id: str, model_id: str) -> str:
    lookup = _DYNAMIC_GENERAL_MODEL_LABELS.get(provider_id, {})
    return lookup.get(model_id, model_id)


def resolve_known_general_model_ids(provider_id: str) -> list[str]:
    normalized_provider = provider_id.strip().lower()
    return list(_DYNAMIC_GENERAL_MODEL_LABELS.get(normalized_provider, {}).keys())


def resolve_provider_function_model_catalog(
    provider_id: str,
    *,
    available_models: list[str] | None = None,
) -> list[dict[str, Any]]:
    normalized_provider = provider_id.strip().lower()
    general_models = list(
        dict.fromkeys(
            [str(model).strip() for model in (available_models or []) if str(model).strip()]
            + resolve_known_general_model_ids(normalized_provider)
        )
    )
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for model_id in general_models:
        normalized_model = str(model_id).strip()
        if not normalized_model:
            continue
        entry_key = ("general", normalized_model)
        if entry_key in seen:
            continue
        seen.add(entry_key)
        items.append(
            {
                "provider_id": normalized_provider,
                "model_id": normalized_model,
                "title": _general_model_title(normalized_provider, normalized_model),
                "function_id": "general",
                "description": "Modelo geral do provider.",
                "status": "current",
            }
        )

    for definition in _STATIC_PROVIDER_MODELS:
        if definition.provider_id != normalized_provider:
            continue
        entry_key = (definition.function_id, definition.model_id)
        if entry_key in seen:
            continue
        seen.add(entry_key)
        items.append(
            {
                "provider_id": definition.provider_id,
                "model_id": definition.model_id,
                "title": definition.title,
                "function_id": definition.function_id,
                "description": definition.description,
                "status": definition.status,
            }
        )

    items.sort(
        key=lambda item: (
            MODEL_FUNCTION_IDS.index(str(item["function_id"]))
            if str(item["function_id"]) in MODEL_FUNCTION_IDS
            else len(MODEL_FUNCTION_IDS),
            str(item["title"]).lower(),
        )
    )
    return items


def build_function_model_catalog(
    provider_catalog: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    by_function: dict[str, list[dict[str, Any]]] = {function_id: [] for function_id in MODEL_FUNCTION_IDS}
    for provider_id, payload in provider_catalog.items():
        provider_title = str(payload.get("title") or provider_id)
        provider_vendor = str(payload.get("vendor") or provider_title)
        category = str(payload.get("category") or "general")
        command_present = bool(payload.get("command_present", False))
        enabled = bool(payload.get("enabled", False))
        functional_models = resolve_provider_function_model_catalog(
            provider_id,
            available_models=[str(item) for item in payload.get("available_models") or []],
        )
        for model in functional_models:
            function_id = str(model["function_id"])
            by_function.setdefault(function_id, []).append(
                {
                    **model,
                    "provider_title": provider_title,
                    "provider_vendor": provider_vendor,
                    "provider_category": category,
                    "provider_enabled": enabled,
                    "command_present": command_present,
                }
            )
    for function_id in list(by_function):
        by_function[function_id].sort(
            key=lambda item: (str(item["provider_title"]).lower(), str(item["title"]).lower())
        )
    return by_function
